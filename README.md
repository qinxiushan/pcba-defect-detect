# YOLO26 PCB 缺陷检测

本仓库用于使用 Ultralytics YOLO26 在 PCB 缺陷数据集上进行目标检测，并与同伴负责的其他 YOLO 版本进行对比。

## 数据集

数据配置位于 `pcb-defect-dataset/data.yaml`，包含 6 个类别：

- `mouse_bite`
- `spur`
- `missing_hole`
- `short`
- `open_circuit`
- `spurious_copper`

数据集目录应包含 `train/`、`val/` 和 `test/`，每个目录中按照 YOLO 检测格式分别存放图片和标签。原始图片、标签和本地数据不提交到 GitHub。

## 环境

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 训练

```powershell
python scripts/train_detect.py
```

最佳权重输出到 `runs/yolo26n_pcb_detect/weights/best.pt`。显卡、训练轮数和输入尺寸等实验参数统一写在脚本中，便于与其他 YOLO 版本公平比较。

## 验证

```powershell
python scripts/validate_detect.py
```

验证时重点记录 mAP50-95、mAP50、Precision、Recall、训练时间和推理速度。