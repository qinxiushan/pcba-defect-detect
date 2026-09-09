# YOLOv11n 模型接入验证

验证日期：2026-09-09。**当前运行的 FastAPI 已接入真实 YOLOv11n PCB 缺陷检测模型，HTTP 验证全部通过。**

## 当前模型与环境

- 页面名称：`我的模型 · YOLOv11n（GPU）`；模型 ID：`member-yolov11`。
- 版本：`yolov11n-20260908`，来源为已完成 100 轮训练的 `runs/pcb_defects_yolo11n-2/weights/best.pt`。
- 固定权重副本：`backend/weights/member-yolov11n-20260908.pt`。
- SHA-256：`8975896f33816824a6ba56b3618275a05f946a46cf9ee4570dd5285b69413659`，文件大小 5,559,392 字节；清单见 `backend/weights.manifest.json`。
- 运行环境：conda 环境 `D:\conda-envs\yolov11`，Python 3.10.21、Torch 2.5.1+cu124、torchvision 0.20.1+cu124、Ultralytics 8.4.138。
- 推理使用 GPU（device=0，NVIDIA RTX 4060 Laptop GPU，CUDA 12.4）；CPU 也可推理，已通过 `verify_yolo.py` 验证。
- 类别名与系统六类完全一致（`mouse_bite, spur, missing_hole, short, open_circuit, spurious_copper`），无需 `class_map`。

## 模型性能

| 指标 | val（1066 张） | test（1068 张） |
|---|---|---|
| mAP50 | 0.9921 | 0.825 |
| mAP50-95 | 0.6668 | — |
| 精确率 P | 0.9828 | 0.811 |
| 召回率 R | 0.9912 | 0.750 |

各类别 val AP50：missing_hole 0.978、spur 0.99、mouse_bite 0.99、open_circuit 1.00、spurious_copper 1.00、short 0.98。

## 样例图推理

样例图：`light_01_missing_hole_02_2_600.jpg`（600×600），来源 val 集。

`verify_yolo.py` 独立加载（CPU 新进程）输出：

```json
{
  "image_size": [600, 600],
  "device": "cpu",
  "detections": [
    {
      "class_id": 2,
      "class_name": "missing_hole",
      "confidence": 0.7835,
      "bbox_xyxy": [175.27, 107.28, 205.08, 140.49]
    }
  ]
}
```

HTTP API 推理（GPU，与 mock 模型对比）：

| 模型 | is_mock | 检出数 | 置信度 | load_ms | inference_ms |
|---|---|---|---|---|---|
| member-yolov11（真实） | false | 1 | 0.783 | 0（缓存命中） | 14.3 |
| demo-a（模拟） | true | 3 | — | — | — |

## 接入验收

| 验收项 | 结果 |
|---|---|
| verify_yolo.py 独立加载（新进程 CPU） | ✅ 通过 |
| 类别映射验证 | ✅ 模型类名与系统六类完全一致，无需 class_map |
| 空检测验证（conf=0.99） | ✅ 返回空列表，状态 succeeded |
| 极小目标 | ✅ 最小框面积 990.2 px²，坐标合法 |
| 非正方形图片（500×300） | ✅ 检出 1 个缺陷，坐标全部在 0≤x1<x2≤500, 0≤y1<y2≤300 范围内 |
| 边界坐标 | ✅ 所有框 x1≥0, x2≤width, y1≥0, y2≤height |
| 同图与 mock 对比 | ✅ 真实模型 is_mock=false 检出 1 个缺陷；mock 模型 is_mock=true 检出 3 个 |
| 权重缺失不阻止 API | ✅ baseline 权重缺失显示 available=false，但 API 正常运行 |

验收结果文件：`backend/weights/acceptance_results.json`（本地运行数据，不提交 Git）。
验收脚本：`backend/acceptance_test.py`。

## 直接使用

1. 刷新 http://127.0.0.1:5173 。
2. 在工作台勾选 **我的模型 · YOLOv11n（GPU）**，上传图片并开始检测。
3. 在"检测历史"查看结果。原来的两个演示模型仍标注"模拟"。

重复验证命令（服务启动后，在 backend 目录运行）：

```powershell
D:\conda-envs\yolov11\python.exe acceptance_test.py
```

独立加载验证（不依赖后端）：

```powershell
D:\conda-envs\yolov11\python.exe scripts\verify_yolo.py --weights weights/member-yolov11n-20260908.pt --image weights/sample_pcb.jpg
```

这是接入与功能冒烟测试，没有计算完整测试集 mAP（训练阶段已计算），也没有据此宣称模型准确率达标。
