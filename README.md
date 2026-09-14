# PCB Insight · PCB 缺陷检测展示系统

服务器自动发布：配置 [GitHub Actions CI/CD](docs/ci-cd.md) 后，main 分支测试通过即自动部署，健康检查失败回退。

已集成四个 YOLO 模型配置及独立的 [VLM 零样本检测](docs/vlm-detection.md)。VLM 直接读取原图，检测框和判断说明保存至数据库，可在历史记录中恢复。

供团队共享的 React + FastAPI 推理展示系统。统一图片输入和检测结果协议，让不同成员的模型通过适配器接入同一套界面。

本次共享内容为前后端系统和接入文档，**不包含训练代码、数据集、日志或模型权重**。默认目录包含四位成员的 YOLO 模型和一个云端 VLM，不注册演示模型。

## 功能与架构

- 单图上传、置信度阈值、模型常驻与有限并行推理，YOLO 和云端 VLM 独立调度、并排对比。
- 检测框缩放和显隐、类别统计、模型版本与耗时展示。
- SQLite 本地历史、JSON 和带框 PNG 导出。
- 模拟适配器与真实 Ultralytics YOLO 适配器，默认 CPU 推理。

前端使用 React、TypeScript、Vite、Ant Design 和 TanStack Query；后端使用 Python 3.11、FastAPI、Pydantic、SQLAlchemy 和 uv。前端通过 `/api/v1` 调用统一业务接口，模型特有的加载、预处理、后处理与类别映射由适配器负责。

## 启动当前版本（YOLO＋VLM）

准备 Node.js 22 LTS、npm 和 uv，在仓库根目录分别打开两个终端。

以下为 Windows PowerShell 命令；使用 `npm.cmd` 避免 npm.ps1 执行策略限制，macOS/Linux 使用 `npm`。每个带 `cd backend` 或 `cd frontend` 的独立代码块从仓库根目录开始，已经在目标目录时不要重复切换。

VLM 密钥填写在仓库根目录 `.env` 或 `backend/.env` 的 `QWEN_API_KEY`，不需要写进启动命令。YOLO 需要对应本地权重；VLM 无需 YOLO 权重。

后端：

```powershell
cd backend
uv sync --locked --python 3.11 --extra yolo --extra qwen
$env:PCB_MODELS_CONFIG = (Resolve-Path models.json).Path
uv run --extra yolo --extra qwen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1
```

访问 http://127.0.0.1:5173 。缺少权重或密钥时 API 仍可启动，对应模型显示“未就绪”；YOLO 检测需准备权重，VLM 检测需有效云端密钥。模拟适配器仅保留用于自动测试和显式开发配置。

接口文档：http://127.0.0.1:8000/docs 。前端的 `/api` 由 Vite 转发至本机 8000 端口，无需直接跨域访问。

## 接入成员的真实模型

1. 单独获取固定版本权重、模型定义、依赖版本及类别映射；权重不通过 Git 分发。
2. 在 `backend/models.json` 注册模型，权重路径相对于配置文件解析。
3. 安装推理依赖并重启后端：

```powershell
cd backend
uv sync --locked --python 3.11 --extra yolo --extra qwen
uv run --extra yolo --extra qwen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

4. 刷新页面、选择真实模型，用成员提供的样例图验证，并确认结果的 `is_mock=false`。

权重统一命名为 `backend/weights/pcb-模型名-YYYYMMDD.pt`。当前模型、作者和版本见 [模型目录说明](docs/model-catalog.md)，实际文件校验信息见 `backend/weights.manifest.json`。权重需另行分发。

**业务接口与模型架构解耦，但每种模型仍需要适配器。** 标准输出为类别、置信度及方向校正后的原图像素坐标 `bbox_xyxy`。类别为鼠咬、毛刺、缺失孔、短路、开路和杂铜。

完整交付清单、配置示例与适配器模板见 [模型接入指南](docs/model-integration.md)。当前 Windows/Linux 使用锁定的官方 CPU 版 Torch；启用 GPU 需要匹配运行时，仅修改 `device` 不会安装 CUDA 依赖。

## 目录

| 路径                                            | 用途                              |
| ----------------------------------------------- | --------------------------------- |
| `frontend/`                                   | React 界面、组件测试与 npm 锁文件 |
| `backend/app/`                                | API、数据库、模型适配器与统一类型 |
| `backend/tests/`                              | 不依赖真实权重的业务测试          |
| `backend/scripts/`                            | 可选的真实推理验证脚本            |
| `backend/models.json`                         | 受控模型注册                      |
| `backend/pyproject.toml`、`backend/uv.lock` | Python 依赖与可选推理环境         |
| `docs/`                                       | 接入指南和验证记录                |
| `AGENTS.md`                                   | 代码协作约定                      |

`backend/data/`、`backend/weights/`、虚拟环境、node_modules 和构建产物均不提交。真实验证脚本中的数据集路径是可选的本地输入，不是启动系统所需的仓库依赖。

## 测试与构建

```powershell
cd backend
uv run --extra yolo --extra qwen pytest -q
```

后续同步、启动、测试都保留 `--extra yolo --extra qwen`，避免 uv 同步时移除可选依赖。

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

当前改造已通过 27 项后端测试、3 项前端组件测试和生产构建。VLM 真实调用及持久化验证的结果与限制见 [VLM 检测说明](docs/vlm-detection.md)；旧基线报告保留于 [真实模型验证报告](docs/real-model-validation.md)，不代表当前所有模型的准确率。

真实 VLM 单图验证（先自备 `backend/weights/sample_pcb.jpg`；会向云端发送图片并产生费用）：

```powershell
cd backend
uv run --extra yolo --extra qwen python scripts/verify_vlm.py --image weights/sample_pcb.jpg
```

脚本无需另起 FastAPI，使用隔离数据库，不会在默认工作台历史中新增记录。

## 使用边界

- 面向本机或受信任的局域网，没有账号与权限系统。
- 每个数据目录仅由一个 Uvicorn worker 管理，最多 20 个未结束任务。本地默认一个推理槽位，VLM 默认两个独立槽位；模型首次加载后常驻。服务器部署、共享密码和并发验收见 [演示部署](docs/demo-deployment.md)。
- 不包含在线训练、视频、批量推理或完整准确率评估。
- 图片限制为 JPEG/PNG、10 MB、2500 万像素；未检出缺陷不等同于产品合格。

环境变量、局域网访问及存储说明见 [后端说明](backend/README.md)。
