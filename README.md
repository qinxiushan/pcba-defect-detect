# PCB Insight · PCB 缺陷检测展示系统

供团队共享的 React + FastAPI 推理展示系统。统一图片输入和检测结果协议，让不同成员的模型通过适配器接入同一套界面。

本次共享内容为前后端系统和接入文档，**不包含训练代码、数据集、日志或模型权重**。没有权重也能通过模拟模型开发和演示。

## 功能与架构

- 单图上传、置信度阈值、多模型串行推理与并排对比。
- 检测框缩放和显隐、类别统计、模型版本与耗时展示。
- SQLite 本地历史、JSON 和带框 PNG 导出。
- 模拟适配器与真实 Ultralytics YOLO 适配器，默认 CPU 推理。

前端使用 React、TypeScript、Vite、Ant Design 和 TanStack Query；后端使用 Python 3.11、FastAPI、Pydantic、SQLAlchemy 和 uv。前端通过 `/api/v1` 调用统一业务接口，模型特有的加载、预处理、后处理与类别映射由适配器负责。

## 克隆后启动：无需权重

准备 Node.js 22 LTS、npm 和 uv，在仓库根目录分别打开两个终端。

后端：

```powershell
cd backend
uv sync --locked --python 3.11
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

访问 http://127.0.0.1:5173 ，上传 JPEG/PNG 并选择演示模型。真实权重或推理依赖缺失时，真实模型显示“未就绪”，不会妨碍模拟流程。模拟结果不代表实际缺陷。

接口文档：http://127.0.0.1:8000/docs 。前端的 `/api` 由 Vite 转发至本机 8000 端口，无需直接跨域访问。

## 接入成员的真实模型

1. 单独获取固定版本权重、模型定义、依赖版本及类别映射；权重不通过 Git 分发。
2. 在 `backend/models.json` 注册模型，权重路径相对于配置文件解析。
3. 安装推理依赖并重启后端：

```powershell
cd backend
uv sync --locked --extra yolo
uv run --extra yolo uvicorn app.main:app --host 127.0.0.1 --port 8000
```

4. 刷新页面、选择真实模型，用成员提供的样例图验证，并确认结果的 `is_mock=false`。

已有基线配置引用 `backend/weights/pcb-yolov8s-baseline-20260908.pt`，该文件需另行分发；校验信息见 `backend/weights.manifest.json`。其他成员可以添加自己的模型，不需要此基线文件。

**业务接口与模型架构解耦，但每种模型仍需要适配器。** 标准输出为类别、置信度及方向校正后的原图像素坐标 `bbox_xyxy`。类别为鼠咬、毛刺、缺失孔、短路、开路和杂铜。

完整交付清单、配置示例与适配器模板见 [模型接入指南](docs/model-integration.md)。当前 Windows/Linux 使用锁定的官方 CPU 版 Torch；启用 GPU 需要匹配运行时，仅修改 `device` 不会安装 CUDA 依赖。

## 目录

| 路径 | 用途 |
|---|---|
| `frontend/` | React 界面、组件测试与 npm 锁文件 |
| `backend/app/` | API、数据库、模型适配器与统一类型 |
| `backend/tests/` | 不依赖真实权重的业务测试 |
| `backend/scripts/` | 可选的真实推理验证脚本 |
| `backend/models.json` | 受控模型注册 |
| `backend/pyproject.toml`、`backend/uv.lock` | Python 依赖与可选推理环境 |
| `docs/` | 接入指南和验证记录 |
| `AGENTS.md` | 代码协作约定 |

`backend/data/`、`backend/weights/`、虚拟环境、node_modules 和构建产物均不提交。真实验证脚本中的数据集路径是可选的本地输入，不是启动系统所需的仓库依赖。

## 测试与构建

```powershell
cd backend
uv run pytest -q
```

已经启用真实推理环境时，改用 `uv run --extra yolo pytest -q`，避免 uv 同步时移除可选依赖。

```powershell
cd frontend
npm test
npm run build
```

本地已通过 9 项后端测试、2 项前端组件测试和生产构建；真实基线完成了六类图片的 HTTP 推理与导出验证，见 [真实模型验证报告](docs/real-model-validation.md)。这不代表所有成员模型都已兼容，也不代表完整测试集准确率。

## 使用边界

- 面向本机或受信任的局域网，没有账号与权限系统。
- 每个数据目录仅由一个 Uvicorn worker 管理，最多 20 个未结束任务，推理串行执行。
- 不包含在线训练、视频、批量推理或完整准确率评估。
- 图片限制为 JPEG/PNG、10 MB、2500 万像素；未检出缺陷不等同于产品合格。

环境变量、局域网访问及存储说明见 [后端说明](backend/README.md)。
