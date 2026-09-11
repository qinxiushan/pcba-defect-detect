# YOLO26 PCB 缺陷检测 Baseline

## 实验配置

| 项目 | 值 |
|---|---|
| 模型 | YOLO26n |
| 任务 | 目标检测 |
| Ultralytics | 8.4.144 |
| Python | 3.10.11 |
| PyTorch | 2.14.0+cpu |
| 训练轮数 | 50 |
| 输入尺寸 | 640 x 640 |
| 优化器 | AdamW（optimizer=auto） |
| 随机种子 | 42 |
| 设备 | CPU（12th Gen Intel Core i7-12650H） |
| 训练集 | 8,534 张图片 |
| 验证集 | 1,066 张图片 |
| 测试集 | 1,068 张图片，1,662 个实例 |
| 模型参数量 | 2,506,140（训练结构） |
| 最佳权重 | `runs/yolo26n_pcb_baseline-2/weights/best.pt` |
| 训练结果 | `runs/yolo26n_pcb_baseline-2/results.csv` |

## 验证集结果

最佳验证集 mAP50-95 出现在第 46 轮。

| 指标 | 最佳轮次（Epoch 46） | 最后一轮（Epoch 50） |
|---|---:|---:|
| Precision | 0.98224 | 0.98322 |
| Recall | 0.98224 | 0.98048 |
| mAP50 | 0.99034 | 0.99051 |
| mAP50-95 | **0.57317** | 0.57153 |

训练总耗时约 110,995 秒，即 30.83 小时，受 CPU 训练速度影响较大。

## 独立测试集结果

使用第 46 轮保存的 `best.pt`，在未用于训练和模型选择的 `test` 集上评估。

| 指标 | 数值 |
|---|---:|
| Precision | **0.97865** |
| Recall | **0.98669** |
| mAP50 | **0.98998** |
| mAP50-95 | **0.56798** |

### 各类别 AP（测试集）

| 类别 | Precision | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|
| mouse_bite | 0.978 | 1.000 | 0.990 | 0.55345 |
| spur | 0.985 | 0.986 | 0.994 | 0.57639 |
| missing_hole | 0.973 | 0.996 | 0.994 | **0.60440** |
| short | 0.976 | 0.978 | 0.988 | 0.56758 |
| open_circuit | 0.992 | 0.987 | **0.995** | 0.55706 |
| spurious_copper | 0.967 | 0.973 | 0.979 | 0.54898 |

## 推理速度

测试集评估输出的单张图片平均耗时：

- 预处理：0.9 ms
- 模型推理：37.9 ms
- 后处理：0.5 ms
- 合计约：39.3 ms/张，约 25.4 FPS

## 结果文件

- 训练曲线：[runs/yolo26n_pcb_baseline-2/results.png](../runs/yolo26n_pcb_baseline-2/results.png)
- 混淆矩阵：[runs/yolo26n_pcb_baseline-2/confusion_matrix.png](../runs/yolo26n_pcb_baseline-2/confusion_matrix.png)
- 测试集评估目录：`runs/detect/runs/yolo26n_pcb_test/`
