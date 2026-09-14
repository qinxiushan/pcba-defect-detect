#!/usr/bin/env bash
# Run as pcb-deploy, never root. Runtime state and secrets are outside releases.
set -Eeuo pipefail
umask 022
release_id=${1:?release id required}
checksum=${2:?sha256 required}
[[ "$release_id" =~ ^[a-f0-9]{40}-[0-9]+-[0-9]+$ ]] || exit 2
[[ "$checksum" =~ ^[a-f0-9]{64}$ ]] || exit 2
root=/opt/pcb
archive="$root/incoming/$release_id.tar.gz"
release="$root/releases/$release_id"
exec 9> "$root/.deploy.lock"
flock -w 120 9
[[ ! -e "$release" ]] || { echo 'Release already exists; rerun the GitHub job to get a new attempt ID.' >&2; exit 2; }
[[ ! -e "$root/current" || -L "$root/current" ]] || { echo 'current must be a symlink' >&2; exit 2; }
previous=$(readlink -f "$root/current" || true)
if [[ -n "$previous" && -e "$root/current" ]]; then
    [[ "$previous" == "$root/releases/"* && -d "$previous" ]] || exit 2
else
    previous=''
fi
printf '%s  %s\n' "$checksum" "$archive" | sha256sum -c -
mkdir "$release"
# The archive is built from explicit trusted main paths; reject traversal and links.
python3 - "$archive" "$release" <<'PY'
import pathlib, sys, tarfile
with tarfile.open(sys.argv[1]) as archive:
    for member in archive.getmembers():
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
            raise ValueError('Unsafe release member')
        if not (member.name in ('backend', 'frontend') or member.name.startswith(('backend/', 'frontend/'))):
            raise ValueError('Unexpected release path')
    archive.extractall(sys.argv[2], filter='data')
PY
ln -s "$root/shared/weights" "$release/backend/weights"
cd "$release/backend"
uv sync --locked --python /usr/bin/python3.11 --no-dev --extra yolo --extra qwen
.venv/bin/python -c 'import app.main, torch, ultralytics, dashscope'
[[ -s "$release/frontend/dist/index.html" ]]

activate() {
    ln -sfnT "$1" "$root/.current-$release_id"
    mv -Tf "$root/.current-$release_id" "$root/current"
}
healthy() {
    local attempt=0
    while (( attempt < 30 )); do
        attempt=$((attempt + 1))
        if curl --fail --silent --max-time 3 http://127.0.0.1:8000/api/v1/health |
            python3 -c 'import json,sys; x=json.load(sys.stdin); sys.exit(0 if x.get("status")=="ok" and x.get("worker_alive") is True else 1)' 2>/dev/null; then
            return 0
        fi
        sleep 2
    done
    return 1
}
rollback() {
    trap - ERR HUP INT TERM
    echo 'Deployment failed; restoring previous code release.' >&2
    if [[ -n "$previous" ]]; then
        activate "$previous"
        sudo -n /usr/bin/systemctl restart pcb
        healthy || echo 'CRITICAL: previous release is also unhealthy; inspect journalctl -u pcb.' >&2
    else
        sudo -n /usr/bin/systemctl stop pcb
        echo 'First deployment failed; no previous release exists.' >&2
    fi
    exit 1
}
# Dependencies are prepared before touching the live service. Only one worker may use the DB.
trap rollback ERR HUP INT TERM
activate "$release"
sudo -n /usr/bin/systemctl restart pcb
healthy
trap - ERR HUP INT TERM
printf '%s\n' "$previous" > "$root/previous-release"
echo "Deployed $release_id"
