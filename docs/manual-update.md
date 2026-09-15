# 当前手工部署的更新方式

适用于当前服务器：代码在 `/home/ubuntu/pcba-defect-detect`，systemd 的 `pcb` 服务以 ubuntu 用户运行，使用该目录下的虚拟环境、`backend/models.json` 和 `backend/data`。前端位于 `/var/www/pcb`，Nginx 8080 端口代理后端 8000 端口。它与 `/opt/pcb/current` 的自动发布布局不同，未统一布局前保持 `DEPLOY_ENABLED` 关闭。

## 林朴同学的 YOLO26n

根目录 `best.pt` 已复制为 `backend/weights/pcb-yolov26n-20260912.pt`。模型 ID 仍为 `pcb-yolo26n-baseline`，日期取自 checkpoint 元数据。文件大小 5402181 字节，SHA-256：

```text
c9807e257f4a3ca57a1230dcdb89f46164dc598af435b0a844618b9c39b76ce9
```

代码、模型配置和清单通过 Git 更新；权重必须单独上传，不能提交 Git。

在本机 Windows PowerShell 执行（替换服务器地址）：

```powershell
cd E:\codes\pcba-defect-detect
scp backend/weights/pcb-yolov26n-20260912.pt ubuntu@YOUR_SERVER:~/pcba-defect-detect/backend/weights/
```

上传完成，在服务器执行：

```bash
cd ~/pcba-defect-detect
git pull --ff-only origin main
sha256sum backend/weights/pcb-yolov26n-20260912.pt
```

校验值必须与上方一致；如果 pull 或校验失败，先处理再重启。当前这次模型配置更新不需要重新安装依赖，也不需要重新构建前端。等待正在执行的任务完成后：

```bash
sudo systemctl restart pcb
sudo systemctl status pcb --no-pager
curl --fail http://127.0.0.1:8000/api/v1/health
```

刷新网页选择 YOLOv26n 做一次真实检测，核对历史记录。重启后第一次使用模型需要加载，后续才命中常驻缓存。报错使用 `sudo journalctl -u pcb -n 80 --no-pager`。Ubuntu 24.04 如果 OpenCV 报缺少 libGL.so.1，执行 `sudo apt install -y libgl1`。

## 启用 VLM

当前手工服务没有读取 `/etc/pcb/pcb.env` 的 EnvironmentFile；应用会读取仓库根目录 `.env` 和 `backend/.env`，其中 backend 文件优先，进程环境变量优先级最高。推荐只在服务器 `backend/.env` 配置云端密钥，不复制整份本机环境配置。

```bash
cd ~/pcba-defect-detect/backend
touch .env
chmod 600 .env
nano .env
```

添加或修改（不要保留示例值，不要在聊天或 Git 中发送真实密钥）：

```dotenv
QWEN_API_KEY=your-real-key
```

然后 `sudo systemctl restart pcb`。本次若同时更新权重和密钥，最后统一重启一次即可。已安装 qwen extra，无需额外启动 VLM 进程；在前端选择 Qwen VLM 零样本检测并提交图片。

模型显示“可用”只说明凭据和 SDK 存在，真正能否调用还取决于密钥权限、服务账号状态与服务器网络；需一次真实请求验收。原图会发送到云端，可能计费；当前默认 UTC 每天最多 100 次尝试，失败计入。查看任务结果中的判断、检测框和历史记录；0 个框或 uncertain 不代表接口未接通。

## 以后更新

仅配置或后端代码变更：pull 后重启 pcb；依赖文件变更时，在 backend 用 `uv sync --locked --python /usr/bin/python3.11 --extra yolo --extra qwen` 更新依赖后重启。前端代码变更时另执行 `npm ci`、`npm run build`，再将 `frontend/dist/.` 复制到 `/var/www/pcb/`。不要清空 data 或覆盖服务器 `.env`。
