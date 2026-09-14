# GitHub Actions 自动部署

PR 自动测试；main 更新后自动测试、构建前端、打包，通过 SSH 上传到 Ubuntu/Debian，安装锁定依赖，切换版本并重启 `pcb`。健康检查失败时切回上一版。也可在 Actions 页面选择 **CI and demo deployment → Run workflow → main** 重新发布。

配置在 `.github/workflows/ci-cd.yml`，无需 Docker 或镜像仓库，服务器也不需要 Node.js。GitHub runner 必须能访问服务器 SSH，服务器必须能下载 Python 依赖。

## 一次性准备服务器

沿用 [演示部署](demo-deployment.md) 的 Nginx、HTTPS、共享密码、`pcb` 服务用户和 `/var/lib/pcb`。以下在服务器管理员 shell 执行，示例源码位于 `/opt/pcb`。已有部署先备份配置，不覆盖数据库、图片或密钥。

准备 `/usr/bin/python3.11`、`python3`（3.11.8+）、`uv`（0.12.5）、curl、tar、flock、sha256sum、sudo。uv 需在非交互 SSH 的 PATH 中，例如 `/usr/local/bin/uv`。使用系统 Python，避免 systemd 的 ProtectHome 阻止读取用户目录里的解释器。

```bash
sudo adduser --disabled-password --gecos '' pcb-deploy
sudo install -d -o pcb-deploy -g pcb-deploy -m 755 /opt/pcb/releases /opt/pcb/incoming /opt/pcb/shared /opt/pcb/shared/weights
sudo chown pcb-deploy:pcb-deploy /opt/pcb
sudo install -d -o pcb-deploy -g pcb-deploy -m 700 /home/pcb-deploy/.ssh
sudo install -m 440 -o root -g root /opt/pcb/backend/deploy/pcb-deploy.sudoers /etc/sudoers.d/pcb-deploy
sudo visudo -cf /etc/sudoers.d/pcb-deploy
```

部署账号只有重启/停止 `pcb` 的 sudo 权限。把专用部署公钥加入 `/home/pcb-deploy/.ssh/authorized_keys`，文件归属 pcb-deploy、权限 600；建议公钥前加 `restrict` 禁止端口转发等功能。私钥存 GitHub Secret，不放仓库或聊天。

将固定权重放入 `/opt/pcb/shared/weights/`，名称与 models.json 一致，允许 pcb 用户读取；每版通过软链接使用它们，不覆盖权重。更换模型应先上传固定权重，再发布引用它的配置。

修改 `/etc/pcb/pcb.env` 中两项，保留密钥、并发及额度配置：

```dotenv
PCB_MODELS_CONFIG=/opt/pcb/current/backend/models.json
PCB_DATA_DIR=/var/lib/pcb
```

已有手工部署位于 `/opt/pcb/backend`、`/opt/pcb/frontend` 时，建立初始回退版本（仅首次执行）：

```bash
sudo -u pcb-deploy mkdir /opt/pcb/releases/bootstrap
sudo -u pcb-deploy ln -s /opt/pcb/backend /opt/pcb/releases/bootstrap/backend
sudo -u pcb-deploy ln -s /opt/pcb/frontend /opt/pcb/releases/bootstrap/frontend
sudo -u pcb-deploy ln -s /opt/pcb/releases/bootstrap /opt/pcb/current
```

确认旧虚拟环境和前端 dist 可用。空服务器跳过 bootstrap，首次发布失败时没有旧版可回退。

```bash
sudo install -m 644 /opt/pcb/backend/deploy/pcb-release.service /etc/systemd/system/pcb.service
sudo systemctl daemon-reload
sudo systemctl enable pcb
sudoedit /etc/nginx/sites-available/pcb
```

将 Nginx 的 root 改为 `/opt/pcb/current/frontend/dist`，保留 HTTPS、共享密码和 API 代理。执行 `sudo nginx -t` 和 `sudo systemctl reload nginx`。已有可用 bootstrap 时执行 `sudo systemctl restart pcb` 并检查 `curl --fail http://127.0.0.1:8000/api/v1/health`；空服务器等首次 Actions 发布后启动。

## 一次性配置 GitHub

仓库 **Settings → Environments** 创建 `production`，部署分支限制为 `main`。添加 Environment Secrets：

| Secret | 内容 |
| --- | --- |
| DEPLOY_HOST | 服务器 IPv4 或域名，不带协议/路径 |
| DEPLOY_USER | pcb-deploy |
| DEPLOY_PORT | SSH 端口，留空默认 22 |
| DEPLOY_SSH_KEY | 专用部署私钥全文，无交互口令 |
| DEPLOY_KNOWN_HOSTS | 已核验 SSH host key，known_hosts 格式 |

在可信机器用 `ssh-keyscan -p 22 YOUR_HOST` 获取候选 host key，并通过服务器控制台的 `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` 等方式核对指纹。自定义端口保留 `[host]:port` 格式。流水线严格校验主机，不现场自动信任未知 host key。

最后在 **Settings → Secrets and variables → Actions → Variables（仓库级）** 设置 `DEPLOY_ENABLED=true`。未设置时仍测试、构建和保存发布包，部署显示 skipped。不要只在 Environment 设置此开关，因为部署条件在进入 Environment 前求值。

无需设置人工审批即可自动部署；如果组织规则要求审批，GitHub 会等待。密钥及分支限制机制见 [GitHub 官方部署文档](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)。部署密钥只在 main 部署 job 使用，PR 不可访问。

## 日常发布、回退和限制

以后推送或合并到 main 即可，无需手工构建、上传和重启。前后端任一测试失败，部署不会启动。CI 没有真实权重和云端密钥，不调用付费 API；不是准确率或真实模型验收。

发布包仅含后端 app、pyproject.toml、uv.lock、models.json 和构建后的 frontend/dist。不含训练工程、权重、密钥、数据库、图片、虚拟环境。依赖在新目录安装后才原子切换 current；同一时刻只有一个部署，过期 main 提交跳过发布。

重启会短暂中断服务，未完成推理在下次启动标记失败；这不是零停机部署。回退仅恢复代码，不回滚数据。未来如需改数据库结构，必须单独设计兼容迁移。健康检查验证服务和任务线程，不运行真实模型。首次上线及换权重后仍须做真实样例和公网认证验收。

依赖安装失败不影响旧服务；重启或健康检查失败自动回退，Actions 标记失败。首次发布无旧版时停止服务，保留失败版本供排查。服务器断电或强杀进程不在 shell trap 保证范围内，需检查 current 和服务状态。

代码错误但健康接口仍正常时，优先 revert main 的问题提交后重新发布；也可由管理员根据 `/opt/pcb/previous-release` 手动切回并重启。日志在 GitHub Actions 和 `journalctl -u pcb`。

版本目录和上传包暂不自动删除，避免误删回退版本。定期监测磁盘；清理前用 `readlink -f /opt/pcb/current` 核对当前版，至少保留一个可用旧版。`/var/lib/pcb`、`/etc/pcb`、shared/weights 不属于发布清理范围。

Linux 可执行 `python3 backend/deploy/test_release.py` 验证成功发布、重启/健康失败回退、首次失败停止、依赖失败保留旧版、校验和失败及路径穿越拒绝。测试使用临时目录和替代命令，不访问真实服务器。CI 另执行 Bash 语法检查和 ShellCheck。
