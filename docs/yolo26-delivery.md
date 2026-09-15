# YOLO26n PCB 缺陷检测模型交付说明

作者：YOLO26 小组
交付日期：2026-09-15

本文档按照 `docs/model-integration.md` 的模型交付清单整理 YOLO26n 的训练、配置和接入信息。

## 1. 模型与权重

| 项目 | 值 |
|---|---|
| 模型 ID | `pcb-yolo26n-baseline` |
| 名称 | PCB YOLO26n · GPU 100轮基线 |
| 版本 | `gpu-100ep-20260915` |
| 任务 | 目标检测 |
| 权重 | `runs/yolo26n_pcb_gpu_100ep-3/weights/best.pt`（本地，不入 Git） |
| 注册位置 | `backend/models.json` |
| 训练设备 | NVIDIA RTX 4060 Laptop GPU |
| 推理设备 | CPU（共享后端默认配置） |
| 类别数量 | 6 |

权重文件由训练产生，不通过 Git 分发。接入其他成员的环境时，需要将权重放在仓库根目录对应的 `runs/` 路径，或者同步修改 `backend/models.json` 中的 `weights` 字段。

## 2. 训练环境与参数

| 项目 | 值 |
|---|---|
| Python | 3.10.11 |
| Ultralytics | 8.4.152（PyPI 标准版，`pip install "ultralytics>=8.3,<9"`） |
| PyTorch | 2.11.0+cu128 |
| 模型 | `yolo26n.pt` |
| 训练轮数 | 100 |
| 输入尺寸 | 640 x 640 |
| 优化器 | AdamW（`optimizer=auto`） |
| 随机种子 | 42 |
| 数据集 | PCB 六类缺陷数据集 |

> 本次（2026-09-15）改用标准 PyPI ultralytics 8.4.152 重新训练，不再使用早期 8.4.144 定制版的
> `cls_remap / cls_pw / dlog / dlam / dgrad / dis / rle` 定制训练字段，使权重的 forward 与标准
> predict 后处理完全兼容。后端 `backend/.venv` 的 8.4.143 已实测可正常加载并推理该权重。

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
| Precision | 0.98444 |
| Recall | 0.98904 |
| mAP50 | 0.99200 |
| mAP50-95 | 0.60991 |

完整结果见 [YOLO26 baseline 指标报告](../results/yolo26_baseline_metrics.md)。

## 5. 共享系统接入

后端注册项如下：

```json
{"id":"pcb-yolo26n-baseline","adapter":"yolo","device":"cpu","weights":"../runs/yolo26n_pcb_gpu_100ep-3/weights/best.pt"}
```

后端使用 `YoloAdapter` 加载 Ultralytics 权重，输出系统统一的类别、置信度和原图像素坐标 `bbox_xyxy`。模型结果的 `is_mock` 应为 `false`。

> 接入注意：ultralytics `model.predict` 的 ndarray 输入契约是 **HWC BGR uint8**（preprocess 内部
> flip 通道转 RGB，见 predictor.py “BGR to RGB”）。`YoloAdapter.predict` 会把上游传入的 PIL RGB
> 图像转成连续内存的 BGR `ndarray`（`np.asarray(image)[:, :, ::-1]`）后再推理。直接传 RGB 数组会让
> 模型实际收到 BGR，虽然部分简单样本仍可出框，但实测会产生大量错误检测。接入方只需提供 EXIF 校正后的
> RGB PIL 图像，通道转换由适配器完成。
>
> 数据集备注：test 集中有 239 张图片的标注文件沿用旧版 `_256.txt` 后缀（与 `_600.jpg` 图片 stem
> 不匹配），ultralytics 训练和 val 会将其视为无标注背景，本文 mAP 指标按官方配对（829 个
> `_600.txt`）统计。若要利用这批样本，需先在数据集中补全同名 `_600.txt` 标注后重训。
