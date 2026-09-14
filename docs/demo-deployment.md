# 小范围服务器演示

本地已完成的真实模型测量与限制见 [调度验证记录](scheduler-validation.md)。

main 更新后自动发布见 [CI/CD 配置](ci-cd.md)，首次配置后由 GitHub Actions 构建、上传、重启和检查健康状态。

适用于可信体验者共享图片和历史的演示环境，无注册、用户表或个人数据隔离。单进程 FastAPI + SQLite，模型常驻线程内，Nginx 提供 HTTPS、共享密码和前端静态文件。不要设置多个 Uvicorn worker，也不要同时启动两个后端访问相同数据目录。

## 调度配置

设置进程环境变量后重启服务。开发时 PowerShell 用 `$env:PCB_LOCAL_CONCURRENCY = '2'`；生产由 systemd 的 `/etc/pcb/pcb.env` 提供。后端 `.env` 仅用于读取云端凭据，不会自动载入以下调度变量。

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| PCB_LOCAL_CONCURRENCY | 1 | 本地同时执行的模型数，部署测试比较 1、2 |
| PCB_TORCH_THREADS | 2 | 进程启动时设置的 Torch CPU 线程数 |
| PCB_VLM_CONCURRENCY | 2 | 独立云端调用线程数 |
| PCB_VLM_DAILY_LIMIT | 100 | UTC 自然日的云端尝试上限，0 禁止调用 |

每个本地模型一个 FIFO 队列和专属线程，首次请求加载，后续保持常驻；不同模型共享本地并发槽位，同一模型始终串行。云端单独排队，线程分别拥有适配器和 HTTP session。所有主任务最多允许 20 个未完成项；超出返回 HTTP 429。槽位竞争不保证跨模型的严格 FIFO。

任务结果仍写入 `history.sqlite3`，更新、状态汇总、删除使用同一进程内写锁。`vlm-usage.sqlite3` 是独立计费尝试账本，不改变已有历史表；调用前持久化占用额度，失败也计入，删除历史不释放额度。额度耗尽的子任务显示失败原因，本地模型继续完成。没有自动任务重试；SDK 连接错误重试也已禁用。崩溃发生在额度预留后、网络请求前时，该次仍占额度，以保守控制费用。

关闭服务时等待已开始推理退出；排队任务在下次启动时标记中断。重启后成功项保留，其余标记失败，主任务重新汇总。内存队列不负责断点续跑。

`GET /api/v1/health` 保留 `status`、`worker_alive`，新增 `local` 和 `vlm`，各包含 `queued`、`running`（子任务数）、`workers`、`alive`、`concurrency`。线程存活不表示推理一定在进展。其他 API 和导出结构兼容。

## Linux 部署命令

约定仓库位于 `/opt/pcb`，固定权重已单独复制到 `backend/weights`。以下为 Debian/Ubuntu 示例，需要已安装 Python 3.11、uv、Node.js/npm、Nginx 和 apache2-utils。域名 DNS、可信 TLS 证书由管理员准备；将示例域名和证书路径替换为真实值再启用站点。

```bash
cd /opt/pcb/backend
uv sync --locked --python /usr/bin/python3.11 --extra yolo --extra qwen
cd /opt/pcb/frontend
npm ci
npm test
npm run build

sudo useradd --system --home /var/lib/pcb --shell /usr/sbin/nologin pcb
sudo install -d -o pcb -g pcb /var/lib/pcb
sudo install -d -m 750 /etc/pcb
sudo install -m 600 /opt/pcb/backend/deploy/pcb.env.example /etc/pcb/pcb.env
sudoedit /etc/pcb/pcb.env
sudo htpasswd -c /etc/nginx/pcb.htpasswd demo
sudo chown root:www-data /etc/nginx/pcb.htpasswd
sudo chmod 640 /etc/nginx/pcb.htpasswd
sudo install -m 644 /opt/pcb/backend/deploy/pcb.service /etc/systemd/system/pcb.service
sudo install -m 644 /opt/pcb/backend/deploy/nginx.conf /etc/nginx/sites-available/pcb
sudoedit /etc/nginx/sites-available/pcb
sudo ln -s /etc/nginx/sites-available/pcb /etc/nginx/sites-enabled/pcb
sudo nginx -t
sudo systemctl daemon-reload
sudo -u pcb /opt/pcb/backend/.venv/bin/python --version
sudo systemctl enable --now pcb
sudo systemctl reload nginx
sudo systemctl status pcb --no-pager
```

`useradd`、创建符号链接和 `htpasswd -c` 仅首次部署执行；更新共享密码时去掉 `-c`。确保 pcb 用户可读取仓库、虚拟环境和权重，www-data 可读取前端 dist；服务可写目录限制在 `/var/lib/pcb`。后端监听 `127.0.0.1:8000`，服务器仅公开 80/443。Nginx 的共享密码覆盖静态页面及 `/api/`，不直接暴露后端端口。所有体验者均可查看、删除已结束的演示记录。

生产不使用 Vite 开发服务器。更新前端重新 build，更新后端后 `sudo systemctl restart pcb`。通过 `journalctl -u pcb` 查看日志。TLS 使用默认验证；企业代理需要安装可信 CA，并在环境中配置 `REQUESTS_CA_BUNDLE`，不要设置 `verify=False`。

## 验收命令

```bash
# 不携带凭据：以下均应返回 401（图片路径用真实 ID）
curl -I https://demo.example.com/
curl -i https://demo.example.com/api/v1/health
curl -i https://demo.example.com/api/v1/images/IMAGE_ID
# 交互输入共享密码，不写进命令历史；应返回健康 JSON
curl -u demo https://demo.example.com/api/v1/health

cd /opt/pcb/backend
uv run --extra yolo --extra qwen pytest -q
# 样例路径替换为真实 PCB 图片。每次运行在独立目录生成证据，不调用云端。
uv run --extra yolo --extra qwen python scripts/verify_scheduler.py --image /path/to/pcb.jpg --concurrency 1
uv run --extra yolo --extra qwen python scripts/verify_scheduler.py --image /path/to/pcb.jpg --concurrency 2
# 真实付费云端请求及重启持久化验证
uv run --extra yolo --extra qwen python scripts/verify_vlm.py --image /path/to/pcb.jpg --local-model pcb-yolov8s-baseline
```

性能脚本对当前配置中所有可用 YOLO 模型执行两轮，断言第二轮加载耗时为零，然后执行五个并发客户端请求。输出总耗时、各任务耗时、轮询观察到的排队时间和进程 RSS 峰值（50ms 采样，可能漏掉短峰值）。这是目标机器上的进程内真实 API/模型验证，不包含公网和 Nginx 延迟，也不证明模型准确率。比较两份 summary 后选择更适合该机器的并发参数；内存不足时减少启用的模型。

浏览器验证两个页面同时提交，其中一个选择 VLM、另一个选择 YOLO，确认本地结果可先展示，云端完成后补齐。当前仓库提供模板和自动化功能测试，真实域名的证书、认证、服务器容量仍须按上述步骤在目标机器验收。

定期停服务后备份 `/var/lib/pcb`（历史库、额度库及图片一起备份），恢复时同样停服务。演示结束清理不再需要的图片和历史；额度账本不可随历史清空。当前没有自动保留期或磁盘配额，管理员需观察磁盘空间。
