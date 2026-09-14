# PCB 推理 API

独立的 FastAPI 应用，不依赖当前训练进程。默认注册四个 CPU YOLO 模型及一个云端 VLM 零样本检测模型，不注册演示模型。作者与权重命名见 [模型目录说明](../docs/model-catalog.md)。VLM 直接读取原图，其检测结果与说明持久化到任务表，使用方式见 [VLM 检测](../docs/vlm-detection.md)。

## 启动

在仓库根目录打开 PowerShell：

```powershell
cd backend
uv sync --locked --python 3.11 --extra yolo --extra qwen
$env:PCB_MODELS_CONFIG = (Resolve-Path models.json).Path
uv run --extra yolo --extra qwen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

接口文档：http://127.0.0.1:8000/docs 。`uv.lock` 与前端锁文件均应提交到版本库。不要在原 Conda 训练环境里安装 API 依赖。

新终端启动前端：

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1
```

打开 http://127.0.0.1:5173 。上传 JPEG/PNG，勾选已就绪的“PCB YOLOv8s”等模型并开始检测。前端的 `/api` 由 Vite 转发至本机 8000 端口，不需要配置浏览器跨域地址。

不安装 `--extra yolo` 或未提供权重时，API 仍可启动，但对应真实模型显示未就绪。权重放在 `backend/weights/`，文件名与 `models.json` 一致，已忽略 Git 跟踪；其他机器部署时需另行分发。

## 局域网与构建

前后端运行在同一台机器时，后端仍可绑定 `127.0.0.1`，前端使用 `npm.cmd run dev -- --host 0.0.0.0`，队员访问 `http://服务器局域网IP:5173`。请求通过 Vite 代理，按需允许防火墙的 5173 端口。只在受信任的局域网使用，此版本没有账号和权限隔离。

```powershell
cd frontend
npm.cmd run build
npm.cmd run preview -- --host 0.0.0.0
```

构建输出在 `frontend/dist`，preview 默认端口 4173，同样已配置 API 代理。长期托管可使用静态服务器提供 dist，并将 `/api` 反向代理至 FastAPI。Vite dev/preview 用于开发和演示，不作为公网生产部署方案。

必须使用 **一个 Uvicorn worker**，不得设置 `--workers 2` 或同时让多个进程共享同一个数据目录：队列与模型缓存为进程内资源。开发时修改后端需重启，运行中的任务会在下次启动标记失败。

## 配置

| 环境变量              | 默认值                   | 说明                                               |
| --------------------- | ------------------------ | -------------------------------------------------- |
| `PCB_DATA_DIR`      | `backend/data`         | SQLite 和图片持久化目录；推荐绝对路径              |
| `PCB_MODELS_CONFIG` | `backend/models.json`  | 模型注册 JSON；推荐绝对路径                        |
| `PCB_CORS_ORIGINS`  | localhost/127.0.0.1:5173 | 逗号分隔的允许来源；仅前后端直接跨域访问时需要调整 |
| `PCB_TORCH_THREADS` | `2`                    | Torch CPU 计算线程数，减少与训练进程争抢 CPU       |

模型权重路径相对于模型配置文件解析。修改配置后重启后端，历史保留提交时的名称、版本、作者与设备快照。单图创建任务时最多选择 10 个模型；全局最多 20 个未结束任务。每个本地模型独占线程和常驻实例，本地并发默认 1，可通过 `PCB_LOCAL_CONCURRENCY=2` 验证并行；VLM 独立调度，默认并发 2、每日 100 次尝试（UTC）。配置、共享密码部署和验收命令见 [演示部署](../docs/demo-deployment.md)。

耗时分为加载时间与推理时间。推理时间包含适配器的预处理、推理和后处理，不包含排队、网络上传与图片文件读取。不同机器、训练负载和缓存状态会影响耗时，页面不提供准确率或性能排名。

删除记录会删除无其他任务引用的原图；尚未提交推理的上传图片会保留在本地数据目录。演示期间可定期备份后清理整个数据目录以重置全部记录，操作前先停止服务。不要仅删除 SQLite 而保留图片，或在服务运行中修改数据库。

## 接入真实权重

```powershell
cd backend
uv sync --locked --python 3.11 --extra yolo --extra qwen
$env:PCB_MODELS_CONFIG = (Resolve-Path models.json).Path
uv run --extra yolo --extra qwen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

当前配置为 `backend/models.json`；YOLOv8s 固定副本为 `backend/weights/pcb-yolov8s-20260911.pt`，来源是最新完成的 `runs/clean-v2/yolov8s_scale02_seed0-3/weights/best.pt`，默认 CPU。首次安装推理依赖包含 Torch 等较大的软件包；uv 管理依赖不代表模型运行时无需 Torch。不要在读取中的 checkpoint 上覆盖发布，成员应交付固定版本的权重副本。

`uv sync` 未启用相应 extra 时可能移除可选依赖，因此同步、启动和测试均保留 `--extra yolo --extra qwen`，使用文档中的 `uv run --extra yolo --extra qwen`。推理 extra 固定 Torch 2.8.0 / torchvision 0.23.0；Windows/Linux 使用 PyTorch 官方 CPU 源，避免此机器上新版 Torch 的 DLL 初始化失败。将来启用 GPU 时必须调整 `pyproject.toml` 中的 CPU 源和版本并重新锁定，仅修改模型的 `device` 不会安装 CUDA 运行时。配置方法参考 https://docs.astral.sh/uv/guides/integration/pytorch/ 。GPU 驱动和自定义算子仍需独立匹配。

完整成员接入契约见 [模型接入文档](../docs/model-integration.md)。

## 验证

```powershell
cd backend
uv run --extra yolo --extra qwen pytest -q
```

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

真实权重单独验证（从仓库根目录进入 backend；先将自备样例放到 `backend/weights/sample_pcb.jpg`）：

```powershell
cd backend
uv run --extra yolo --extra qwen python scripts/verify_yolo.py --weights weights/pcb-yolov8s-20260911.pt --image weights/sample_pcb.jpg
```

基础业务测试不执行真实 Torch 推理；上述命令保留已启用的可选依赖。验证脚本要求所在环境安装 YOLO 依赖，输出真实检测 JSON，默认 CPU，不训练、不下载缺失权重。

通过正在运行的前后端，对六类缺陷各取一张测试图进行真实 HTTP 验证：

```powershell
cd backend
uv run --extra yolo --extra qwen python scripts/verify_live.py --url http://127.0.0.1:8000/api/v1 --model pcb-yolov8s-baseline --dataset ../pcb-defect-dataset/clean-v2/test
```

脚本按标签文件名排序，为每个类别取第一张有标注的图片，不按检测效果挑图；检查真实模型标记、坐标、JSON/PNG 导出，保留六条历史记录，并将报告与带框图片写入 `backend/data/real-model-verification/`。这是接入冒烟测试，不是完整测试集准确率评估。

## VLM 真实验证

在已配置密钥且同意外发样例、产生 API 费用后运行（从仓库根目录进入 backend；需自备 `weights/sample_pcb.jpg`）：

```powershell
cd backend
uv run --extra yolo --extra qwen python scripts/verify_vlm.py --image weights/sample_pcb.jpg
```

此脚本无需另起服务，使用隔离数据库验证推理和重启恢复；不会写入默认工作台历史。详见 [VLM 检测说明](../docs/vlm-detection.md)。
