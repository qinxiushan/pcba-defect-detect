# 成员模型交付文档 — YOLOv11n PCB 缺陷检测

作者：AIRJUICE <2106620627@qq.com>
交付日期：2026-09-09

本文档按 `docs/model-integration.md` 的成员交付清单编写，覆盖权重版本、网络与依赖、类别映射、预处理/后处理参数、样例图与推理结果。

## 1. 权重与版本信息

| 项目 | 值 |
|---|---|
| 模型 ID | `member-yolov11` |
| 名称 | 我的模型 · YOLOv11n（GPU） |
| 版本 | `yolov11n-20260908` |
| 作者 | AIRJUICE |
| 描述 | YOLOv11n PCB 六类缺陷检测，100 epochs，val mAP50=0.992 / mAP50-95=0.667，GPU 推理 |
| 权重文件 | `backend/weights/member-yolov11n-20260908.pt`（权重不入 Git，单独分发） |
| 文件大小 | 5,559,392 字节（约 5.3 MB） |
| SHA-256 | `8975896f33816824a6ba56b3618275a05f946a46cf9ee4570dd5285b69413659` |
| 注册位置 | `backend/models.json`（device=`"0"` GPU；无 GPU 时可改为 `"cpu"`） |
| 元数据清单 | `backend/weights.manifest.json` |

models.json 注册项：

```json
{"id":"member-yolov11","name":"我的模型 · YOLOv11n（GPU）","version":"yolov11n-20260908","author":"AIRJUICE","description":"YOLOv11n PCB 六类缺陷检测，100 epochs，val mAP50=0.992 / mAP50-95=0.667，GPU 推理。类名与系统六类一致，无需 class_map。","adapter":"yolo","device":"0","weights":"weights/member-yolov11n-20260908.pt"}
```

## 2. 网络定义与依赖

### 网络结构
- 框架：Ultralytics YOLOv11n（yolo11n.yaml）
- 骨干：YOLOv11 C3k2 + C2PSA + SPPF
- 检测头：Detect（解耦头，三尺度输出）
- 无自定义模块；权重为标准 ultralytics checkpoint，无需 `register` 钩子
- 加载入口：`from ultralytics import YOLO; model = YOLO("weights/member-yolov11n-20260908.pt")`

### 依赖版本（交付方验证环境）

| 包 | 版本 |
|---|---|
| Python | 3.10.21 |
| torch | 2.5.1+cu124 |
| torchvision | 0.20.1+cu124 |
| ultralytics | 8.4.138 |
| opencv-python | 5.0.0 |
| Pillow | 12.3.0 |
| numpy | 2.2.6 |
| CUDA | 12.4（GPU 可选，CPU 也可推理） |

后端依赖（fastapi、uvicorn、httpx 等）以 `backend/pyproject.toml` / `uv.lock` 为准，安装 ultralytics 后即可加载本权重。

### 参考运行环境（交付方机器）

- Windows 11，NVIDIA RTX 4060 Laptop GPU（8 GB VRAM），CUDA 12.4
- conda 环境：Python 3.10.21 + torch 2.5.1+cu124
- 后端启动（在 `backend/` 目录）：`python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- 前端启动（在 `frontend/` 目录）：`npm run dev -- --host 127.0.0.1`

## 3. 类别表与映射

### 模型类别（model.names）

| 模型 class_id | 类名 | 系统标准顺序 | 是否一致 |
|---|---|---|---|
| 0 | mouse_bite | 0 | ✅ |
| 1 | spur | 1 | ✅ |
| 2 | missing_hole | 2 | ✅ |
| 3 | short | 3 | ✅ |
| 4 | open_circuit | 4 | ✅ |
| 5 | spurious_copper | 5 | ✅ |

**结论**：模型类别名与 ID 顺序与系统六类完全一致，无需 `class_map` 映射。适配器通过 `CLASS_NAMES.index(result.names[original_id])` 按名匹配。

### 系统标准类别

| 系统 ID | class_name | 中文 |
|---|---|---|
| 0 | mouse_bite | 鼠咬 |
| 1 | spur | 毛刺 |
| 2 | missing_hole | 缺失孔 |
| 3 | short | 短路 |
| 4 | open_circuit | 开路 |
| 5 | spurious_copper | 杂铜 |

## 4. 预处理与后处理参数

### 预处理（由 ultralytics predict 内部完成）
- 输入尺寸：640×640（letterbox 自适应缩放）
- 色彩空间：RGB（ultralytics 内部转换）
- 归一化：像素值 / 255.0，范围 [0, 1]
- 无 mean/std 标准化（ultralytics 默认仅除以 255）
- 输入张量形状：`(1, 3, 640, 640)` float32

### 后处理（由 ultralytics predict 内部完成）
- NMS IoU 阈值：0.45（`iou` 参数，由前端传入，默认 0.45）
- 置信度阈值：由前端传入（默认 0.25）
- 坐标还原：ultralytics 自动将 letterbox 后的坐标还原至原图尺寸
- 输出格式：`boxes.xyxy`（x1, y1, x2, y2 像素坐标，相对原图）

### 适配器处理（YoloAdapter.predict）
- 输入：`PIL.Image`（RGB，已校正 EXIF 方向）
- 坐标钳制：`coords = [max(0, min(v, width/height))]` 确保不越界
- 空框过滤：`x1 >= x2` 或 `y1 >= y2` 的框被丢弃
- 输出：`Detection(class_id, class_name, confidence, bbox_xyxy)` 列表
- 无目标时返回空列表

## 5. 样例图与推理结果

### 样例图
- 仓库内提交副本：`docs/assets/yolov11-sample.jpg`（600×600，70 KB，随 Git 分发）
- 原始来源：val 集 `light_01_missing_hole_02_2_600.jpg`
- 运行时也可放在 `backend/weights/sample_pcb.jpg`（验收脚本默认读取仓库内副本）

### 独立加载验证（verify_yolo.py，CPU 新进程）

在 `backend/` 目录执行：

```powershell
python scripts/verify_yolo.py --weights weights/member-yolov11n-20260908.pt --image ../docs/assets/yolov11-sample.jpg
```

输出：

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

### HTTP API 推理（GPU，与 mock 模型对比）

| 模型 | is_mock | 检出数 | 置信度 | load_ms | inference_ms |
|---|---|---:|---|---:|---:|
| member-yolov11（真实） | false | 1 | 0.783 | 0（缓存命中） | 14.3 |
| demo-a（模拟） | true | 3 | — | — | — |

## 6. 接入验收结果

完整验收脚本：`backend/scripts/acceptance_test.py`（后端启动后，在 `backend/` 目录执行 `python scripts/acceptance_test.py`）。

| 验收项 | 结果 |
|---|---|
| verify_yolo.py 独立加载（新进程 CPU） | ✅ 通过 |
| 类别映射验证 | ✅ 模型类名与系统六类完全一致，无需 class_map |
| 空检测验证（conf=0.99） | ✅ 返回空列表，状态 succeeded |
| 极小目标 | ✅ 最小框面积 990.2 px²，坐标合法 |
| 非正方形图片（500×300） | ✅ 检出 1 个缺陷，坐标全部在 0≤x1<x2≤500, 0≤y1<y2≤300 范围内 |
| 边界坐标 | ✅ 所有框 x1≥0, x2≤width, y1≥0, y2≤height |
| 同图与 mock 对比 | ✅ 真实模型 is_mock=false 检出 1 个缺陷；mock 模型 is_mock=true 检出 3 个 |
| 权重缺失不阻止 API | ✅ 权重缺失的模型显示 available=false 且有原因说明，API 正常运行 |

验收结果 JSON 运行后写入 `backend/weights/acceptance_results.json`（本地运行数据，不提交 Git）。
验证报告详见 `docs/yolov11-validation.md`。

## 7. 权重分发说明

权重文件 `member-yolov11n-20260908.pt`（5.3 MB）按仓库约定不纳入 Git（`*.pt` 在 .gitignore 中）。接入方通过网盘/即时通讯收到权重后：

1. 放入 `backend/weights/member-yolov11n-20260908.pt`；
2. 校验 SHA-256 为 `8975896f33816824a6ba56b3618275a05f946a46cf9ee4570dd5285b69413659`；
3. 重启后端，模型目录中“我的模型 · YOLOv11n（GPU）”显示可用即接入成功。
