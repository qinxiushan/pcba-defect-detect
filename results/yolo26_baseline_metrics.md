# YOLO26 PCB 缺陷检测 Baseline

## 实验配置

| 项目 | 值 |
|---|---|
| 模型 | YOLO26n |
| 任务 | 目标检测 |
| Ultralytics | 8.4.144 |
| Python | 3.10.11 |
| PyTorch | 2.11.0+cu128 |
| 训练轮数 | 100 |
| 输入尺寸 | 640 x 640 |
| 优化器 | MuSGD（optimizer=auto） |
| 随机种子 | 42 |
| 训练设备 | NVIDIA GeForce RTX 4060 Laptop GPU |
| 训练集 | 8,534 张图片 |
| 验证集 | 1,066 张图片 |
| 测试集 | 1,068 张图片，1,662 个实例 |
| 模型参数量 | 2,506,140（训练结构） |
| 最佳权重 | `runs/yolo26n_pcb_gpu_100ep-2/weights/best.pt` |
| 训练结果 | `runs/yolo26n_pcb_gpu_100ep-2/results.csv` |

## 验证集结果

最佳验证集 mAP50-95 出现在第 100 轮。

| 指标 | 最佳轮次（Epoch 100） |
|---|---:|
| Precision | 0.98471 |
| Recall | 0.98728 |
| mAP50 | 0.99047 |
| mAP50-95 | **0.61257** |

训练总耗时约 42,157 秒，即 11.71 小时。训练使用 RTX 4060 GPU，数据加载 worker 为 0。

## 独立测试集结果

使用第 100 轮保存的 `best.pt`，在未用于训练和模型选择的 `test` 集上评估。

| 指标 | 数值 |
|---|---:|
| Precision | **0.98445** |
| Recall | **0.98776** |
| mAP50 | **0.99066** |
| mAP50-95 | **0.61854** |

### 各类别 AP（测试集）

| 类别 | Precision | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|
| mouse_bite | 0.980 | 0.992 | 0.992 | 0.61853 |
| spur | 0.987 | 0.986 | 0.993 | 0.60128 |
| missing_hole | 0.989 | 0.996 | 0.994 | **0.64911** |
| short | 0.982 | 0.983 | 0.993 | 0.62563 |
| open_circuit | 1.000 | 0.996 | **0.995** | 0.61093 |
| spurious_copper | 0.969 | 0.973 | 0.977 | 0.60574 |

## 推理速度

GPU 测试集评估输出的单张图片平均耗时：预处理 0.3 ms，模型推理 3.8 ms，后处理 1.0 ms，合计约 5.1 ms/张，约 196 FPS。

## 结果文件

- 训练曲线：[runs/yolo26n_pcb_gpu_100ep-2/results.png](../runs/yolo26n_pcb_gpu_100ep-2/results.png)
- 混淆矩阵：[runs/yolo26n_pcb_gpu_100ep-2/confusion_matrix.png](../runs/yolo26n_pcb_gpu_100ep-2/confusion_matrix.png)
- 测试集评估目录：`runs/detect/runs/yolo26n_pcb_gpu_100ep_test/`
