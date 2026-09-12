# YOLO26n PCB 缺陷检测模型交付说明

作者：YOLO26 小组
交付日期：2026-09-12

本文档按照 `docs/model-integration.md` 的模型交付清单整理 YOLO26n 的训练、配置和接入信息。

## 1. 模型与权重

| 项目 | 值 |
|---|---|
| 模型 ID | `pcb-yolo26n-baseline` |
| 名称 | PCB YOLO26n · GPU 100轮基线 |
| 版本 | `gpu-100ep-20260912` |
| 任务 | 目标检测 |
| 权重 | `runs/yolo26n_pcb_gpu_100ep-2/weights/best.pt`（本地，不入 Git） |
| 注册位置 | `backend/models.json` |
| 训练设备 | NVIDIA RTX 4060 Laptop GPU |
| 推理设备 | CPU（共享后端默认配置） |
| 类别数量 | 6 |

权重文件由训练产生，不通过 Git 分发。接入其他成员的环境时，需要将权重放在仓库根目录对应的 `runs/` 路径，或者同步修改 `backend/models.json` 中的 `weights` 字段。

## 2. 训练环境与参数

| 项目 | 值 |
|---|---|
| Python | 3.10.11 |
| Ultralytics | 8.4.144 |
| PyTorch | 2.11.0+cu128 |
| 模型 | `yolo26n.pt` |
| 训练轮数 | 100 |
| 输入尺寸 | 640 x 640 |
| 优化器 | AdamW（`optimizer=auto`） |
| 随机种子 | 42 |
| 数据集 | PCB 六类缺陷数据集 |

训练命令：

```powershell
python scripts\train_detect.py
```

验证命令：

```powershell
python scripts\validate_detect.py
```

## 3. 类别映射

模型类别 ID 与系统标准类别一致，不需要 `class_map`：

| ID | 类别 | 中文 |
|---:|---|---|
| 0 | `mouse_bite` | 鼠咬 |
| 1 | `spur` | 毛刺 |
| 2 | `missing_hole` | 缺失孔 |
| 3 | `short` | 短路 |
| 4 | `open_circuit` | 开路 |
| 5 | `spurious_copper` | 杂铜 |

## 4. 性能结果

训练集 8,534 张，验证集 1,066 张，测试集 1,068 张。使用第 100 轮的最佳权重在独立测试集上得到：

| 指标 | 测试集结果 |
|---|---:|
| Precision | 0.98445 |
| Recall | 0.98776 |
| mAP50 | 0.99066 |
| mAP50-95 | 0.61854 |

完整结果见 [YOLO26 baseline 指标报告](../results/yolo26_baseline_metrics.md)。

## 5. 共享系统接入

后端注册项如下：

```json
{"id":"pcb-yolo26n-baseline","adapter":"yolo","device":"cpu","weights":"../runs/yolo26n_pcb_gpu_100ep-2/weights/best.pt"}
```

后端使用 `YoloAdapter` 加载 Ultralytics 权重，输出系统统一的类别、置信度和原图像素坐标 `bbox_xyxy`。模型结果的 `is_mock` 应为 `false`。
