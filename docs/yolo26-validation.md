# YOLO26n 模型验证报告

验证日期：2026-09-12。

## 1. 独立模型评估

YOLO26n 使用 RTX 4060 GPU 完成 100 轮训练后，使用第 100 轮保存的 `best.pt` 在未参与训练和模型选择的 test 集上评估。

| 数据集 | 图片数 | Precision | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|
| val | 1,066 | 0.98471 | 0.98728 | 0.99047 | 0.61257 |
| test | 1,068 | 0.98445 | 0.98776 | 0.99066 | 0.61854 |

测试集各类别 mAP50-95：

| 类别 | mAP50-95 |
|---|---:|
| `mouse_bite` | 0.61853 |
| `spur` | 0.60128 |
| `missing_hole` | 0.64911 |
| `short` | 0.62563 |
| `open_circuit` | 0.61093 |
| `spurious_copper` | 0.60574 |

## 2. 推理速度

GPU 测试集评估的平均耗时为：预处理 0.3 ms、模型推理 3.8 ms、后处理 1.0 ms，合计约 5.1 ms/张，约 196 FPS。

## 3. 结果文件

- 训练记录：`runs/yolo26n_pcb_gpu_100ep-2/results.csv`
- 最佳权重：`runs/yolo26n_pcb_gpu_100ep-2/weights/best.pt`
- 训练曲线：`runs/yolo26n_pcb_gpu_100ep-2/results.png`
- 混淆矩阵：`runs/yolo26n_pcb_gpu_100ep-2/confusion_matrix.png`
- 完整指标说明：`results/yolo26_baseline_metrics.md`

上述权重、训练结果和数据集均为本地文件，不提交到 Git。仓库中已完成模型注册，但共享 FastAPI 的 HTTP 冒烟验收需要在安装 `backend` 依赖并启动服务后执行；本报告不把离线 mAP 结果当作 HTTP 验收结果。

## 4. 共享系统验证命令

在 `backend/` 目录安装并启动真实推理环境：

```powershell
uv sync --locked --extra yolo
uv run --extra yolo uvicorn app.main:app --host 127.0.0.1 --port 8000
```

然后使用前端上传图片并选择 `PCB YOLO26n · GPU 100轮基线`，确认返回结果中的 `is_mock=false`、类别名称和 `bbox_xyxy` 坐标均正确。
