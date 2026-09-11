# PCB Insight：YOLO26 PCB 缺陷检测

本仓库包含团队共用的 PCB 缺陷推理展示系统，以及 YOLO26n 目标检测训练与评估代码。共享系统使用 React + Vite 前端和 FastAPI 后端，不同成员的模型通过后端适配器接入同一套界面。

## YOLO26 数据与训练

数据配置位于 `pcb-defect-dataset/data.yaml`，包含 6 类：`mouse_bite`、`spur`、`missing_hole`、`short`、`open_circuit`、`spurious_copper`。图片和标签保存在本地，不提交到 GitHub。

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\train_detect.py
python scripts\validate_detect.py
```

当前 YOLO26 baseline 使用 50 轮、640 输入尺寸和随机种子 42。最佳权重应位于 `runs/yolo26n_pcb_baseline-2/weights/best.pt`，指标报告位于 `results/yolo26_baseline_metrics.md`。权重和 `runs/` 已加入 `.gitignore`，共享推理前需要每个成员单独准备自己的权重文件。

## 共享推理系统

后端使用 Python 3.11 和 `uv` 管理依赖，前端使用 Node.js 22 LTS 和 npm。分别打开两个终端：

```powershell
cd backend
uv sync --locked --python 3.11
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

访问 `http://127.0.0.1:5173`，API 文档在 `http://127.0.0.1:8000/docs`。

YOLO26 模型已注册在 `backend/models.json`，指向本地训练得到的 `runs/yolo26n_pcb_baseline-2/weights/best.pt`。运行后端时需要安装 YOLO 可选依赖：

```powershell
cd backend
uv sync --locked --extra yolo
uv run --extra yolo uvicorn app.main:app --host 127.0.0.1 --port 8000
```

如果使用仓库根目录的 Python 3.10 环境，也可以确保 `ultralytics` 已安装后运行后端。模型权重不通过 Git 分发。

## 目录

| 路径 | 用途 |
|---|---|
| `frontend/` | React 界面与前端测试 |
| `backend/app/` | FastAPI、数据库、模型适配器和统一接口 |
| `backend/models.json` | 受控模型注册 |
| `pcb-defect-dataset/` | 本地 PCB 检测数据和配置 |
| `scripts/` | YOLO26 训练与验证脚本 |
| `results/` | baseline 指标报告 |
| `docs/` | 模型接入和系统验证文档 |

## 测试

```powershell
cd backend
uv run pytest -q
```

```powershell
cd frontend
npm test
npm run build
```

共享 API 的标准检测输出包含类别、置信度和原图像素坐标 `bbox_xyxy`。完整适配说明见 [docs/model-integration.md](docs/model-integration.md)。
