"""Exercise activation/rollback in temporary directories with fake external services.

No SSH, systemd, real dependencies, secrets or production directories are used.
"""
import hashlib
import io
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('release.sh').read_text(encoding='utf-8')
RELEASE_ID = 'a'*40 + '-123-1'


class ReleaseTest(unittest.TestCase):
    def run_case(self, mode='success', initial=False, unsafe=False, bad_checksum=False):
        with tempfile.TemporaryDirectory(prefix='pcb-release-test-') as directory:
            root = Path(directory)
            for part in ('incoming', 'releases/old', 'shared/weights', 'bin'):
                (root/part).mkdir(parents=True)
            old = root/'releases/old'
            bash = os.getenv('TEST_BASH', shutil.which('bash') or 'bash')
            # Use bash to create symlinks on Git Bash as well as Linux.
            environment = dict(os.environ, TEST_ROOT=root.as_posix(), MODE=mode,
                               TEST_LOG=(root/'commands.log').as_posix())
            if not initial:
                subprocess.run([bash, '-c', 'ln -s "$TEST_ROOT/releases/old" "$TEST_ROOT/current"'], env=environment, check=True)
            archive = root/'incoming'/f'{RELEASE_ID}.tar.gz'
            with tarfile.open(archive, 'w:gz') as output:
                for name in ('backend/app/main.py', 'backend/pyproject.toml', 'frontend/dist/index.html'):
                    data = b'test'
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    output.addfile(member, io.BytesIO(data))
                if unsafe:
                    member = tarfile.TarInfo('../escaped.txt')
                    member.size = 4
                    output.addfile(member, io.BytesIO(b'nope'))
            mocks = {
                'uv': '''[[ "$MODE" != dependencyfail ]] || exit 1
mkdir -p .venv/bin
printf '#!/usr/bin/env bash\nexit 0\n' > .venv/bin/python
chmod +x .venv/bin/python
''',
                'sudo': '''echo "$*" >> "$TEST_LOG"
if [[ "$MODE" == restartfail && $(readlink "$TEST_ROOT/current") != "$TEST_ROOT/releases/old" && "$*" == *restart* ]]; then exit 1; fi
exit 0
''',
                'curl': '''if [[ "$MODE" == unhealthy && $(readlink "$TEST_ROOT/current") != "$TEST_ROOT/releases/old" ]]; then
echo '{"status":"degraded","worker_alive":false}'
else
echo '{"status":"ok","worker_alive":true}'
fi
''',
                'sleep': 'exit 0\n',
                'flock': 'exit 0\n',
                'python3': f'exec {shlex.quote(Path(sys.executable).as_posix())} "$@"\n',
            }
            for name, body in mocks.items():
                path = root/'bin'/name
                path.write_text('#!/usr/bin/env bash\nset -e\n'+body, encoding='utf-8', newline='\n')
                path.chmod(0o755)
            environment['PATH'] = str(root/'bin') + os.pathsep + os.environ['PATH']
            script = root/'release.sh'
            self.assertEqual(SCRIPT.count('root=/opt/pcb'), 1, 'Test must replace the production root exactly once')
            script.write_text(SCRIPT.replace('root=/opt/pcb', 'root='+shlex.quote(root.as_posix())), encoding='utf-8', newline='\n')
            checksum = '0'*64 if bad_checksum else hashlib.sha256(archive.read_bytes()).hexdigest()
            result = subprocess.run([bash, str(script), RELEASE_ID, checksum], env=environment,
                                    text=True, capture_output=True, timeout=30)
            current = subprocess.run([bash, '-c', 'readlink "$TEST_ROOT/current" || true'], env=environment,
                                     capture_output=True, text=True, check=True).stdout.strip()
            commands = (root/'commands.log').read_text() if (root/'commands.log').exists() else ''
            if mode == 'success' and not unsafe and not bad_checksum:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(current, (root/'releases'/RELEASE_ID).as_posix())
                self.assertIn('restart pcb', commands)
            else:
                self.assertNotEqual(result.returncode, 0, result.stdout)
                if not initial:
                    self.assertEqual(current, old.as_posix(), result.stderr)
                if mode == 'dependencyfail' or unsafe or bad_checksum:
                    self.assertEqual(commands, '')
                elif initial:
                    self.assertIn('stop pcb', commands)
                else:
                    self.assertEqual(commands.count('restart pcb'), 2)
            self.assertFalse((root/'escaped.txt').exists())

    def test_success(self):
        self.run_case()

    def test_first_success(self):
        self.run_case(initial=True)

    def test_health_failure_rolls_back(self):
        self.run_case('unhealthy')

    def test_restart_failure_rolls_back(self):
        self.run_case('restartfail')

    def test_dependency_failure_keeps_live_release(self):
        self.run_case('dependencyfail')

    def test_first_failure_stops_service(self):
        self.run_case('unhealthy', initial=True)

    def test_archive_traversal_rejected(self):
        self.run_case(unsafe=True)

    def test_checksum_failure_keeps_live_release(self):
        self.run_case(bad_checksum=True)


if __name__ == '__main__':
    unittest.main()
