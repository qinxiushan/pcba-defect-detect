# YOLO26 PCB 缺陷检测 Baseline

## 实验配置

| 项目 | 值 |
|---|---|
| 模型 | YOLO26n |
| 任务 | 目标检测 |
| Ultralytics | 8.4.152（PyPI 标准版） |
| Python | 3.10.11 |
| PyTorch | 2.11.0+cu128 |
| 训练轮数 | 100 |
| 输入尺寸 | 640 x 640 |
| 优化器 | auto（AdamW） |
| 随机种子 | 42 |
| 训练设备 | NVIDIA GeForce RTX 4060 Laptop GPU |
| 训练集 | 8,534 张图片 |
| 验证集 | 1,066 张图片 |
| 测试集 | 1,068 张图片（其中 239 张因标注仍为旧版 `_256.txt` 后缀被官方配对视为背景），829 个有效标注对、1,662 个实例 |
| 模型参数量 | 2,376,006（fused 推理结构） |
| 最佳权重 | `runs/yolo26n_pcb_gpu_100ep-3/weights/best.pt` |
| 训练结果 | `runs/yolo26n_pcb_gpu_100ep-3/results.csv` |

## 验证集结果

最佳验证集 mAP50-95 出现在第 100 轮。

| 指标 | 最佳轮次（Epoch 100） |
|---|---:|
| Precision | 0.98025 |
| Recall | 0.98861 |
| mAP50 | 0.98901 |
| mAP50-95 | **0.60953** |

训练总耗时约 23,181 秒，即 6.44 小时。训练使用 RTX 4060 GPU，数据加载 worker 为 0。

## 独立测试集结果

使用第 100 轮保存的 `best.pt`，在未用于训练和模型选择的 `test` 集上评估（`conf=0.001`）。

| 指标 | 数值 |
|---|---:|
| Precision | **0.98444** |
| Recall | **0.98904** |
| mAP50 | **0.99200** |
| mAP50-95 | **0.60991** |

### 各类别 AP（测试集）

| 类别 | Precision | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|
| mouse_bite | 0.975 | 0.992 | 0.99209 | 0.61191 |
| spur | 0.986 | 0.986 | 0.99347 | 0.59202 |
| missing_hole | 0.992 | 0.996 | 0.99430 | 0.63451 |
| short | 0.983 | 0.985 | 0.98734 | 0.62247 |
| open_circuit | 0.998 | 0.996 | 0.99500 | 0.59568 |
| spurious_copper | 0.973 | 0.978 | 0.98978 | 0.60285 |

## 结果文件

- 训练曲线：[runs/yolo26n_pcb_gpu_100ep-3/results.png](../runs/yolo26n_pcb_gpu_100ep-3/results.png)
- 混淆矩阵：[runs/yolo26n_pcb_gpu_100ep-3/confusion_matrix.png](../runs/yolo26n_pcb_gpu_100ep-3/confusion_matrix.png)

> 说明：权重与 runs/ 目录均不入 Git，由本地按 `docs/yolo26-delivery.md` 提供。
