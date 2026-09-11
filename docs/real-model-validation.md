# 真实模型接入验证

验证日期：2026-09-08。**当前运行的 FastAPI 已接入真实 PCB YOLOv8s 模型，六类图片 HTTP 验证全部通过。**

## 当前模型与环境

- 页面名称：`PCB YOLOv8s · 真实模型`；模型 ID：`pcb-yolov8s-baseline`。
- 版本：`baseline-20260908`，来源为已完成 30 轮训练的 `runs/detect/runs/exp0_baseline/weights/best.pt`。
- 固定权重副本：`backend/weights/pcb-yolov8s-baseline-20260908.pt`。
- SHA-256：`3a504ab9cd23bbf53b20d34f138b960b563e52f2f512b1f8918bab4bf5a40381`，文件大小 22,514,979 字节；清单见 `backend/weights.manifest.json`。
- 运行环境：后端 `.venv`，Python 3.11、Torch 2.8.0+cpu、torchvision 0.23.0+cpu、Ultralytics 8.4.143；由 uv 和锁文件管理。
- 推理使用 CPU，默认 2 个 Torch 计算线程；未修改原有训练环境、训练脚本或正在训练的权重。

首次安装的 Torch 2.14.0 在此机器上报 `WinError 1114 / c10.dll`，沙箱外也无法导入。替换为官方 CPU 源的固定版本后，独立张量计算及实际模型推理均通过。相关版本和安装源已写入 `pyproject.toml` / `uv.lock`，重装时使用 `uv sync --locked --extra yolo`。

## 六类图片测试

通过 `http://127.0.0.1:5173/api/v1`（与页面相同的 Vite 代理）上传测试集图片并提交真实模型任务。阈值 0.25，每类按标注文件名排序取第一张图片，不按推理效果筛选。

| 类别 | 图片 | 标注数 | 检出数 | 检出置信度 | 推理耗时 ms |
|---|---|---:|---:|---|---:|
| 鼠咬 | l_light_01_mouse_bite_02_2_600.jpg | 1 | 1 | 0.6844 | 3491.96（首次） |
| 毛刺 | l_light_01_spur_02_1_600.jpg | 3 | 3 | 0.7214、0.6221、0.6164 | 146.48 |
| 缺失孔 | l_light_01_missing_hole_04_2_600.jpg | 2 | 2 | 0.7866、0.7800 | 208.95 |
| 短路 | l_light_01_short_03_1_600.jpg | 1 | 1 | 0.7098 | 205.47 |
| 开路 | l_light_01_open_circuit_02_1_600.jpg | 1 | 1 | 0.7756 | 196.19 |
| 杂铜 | l_light_01_spurious_copper_06_2_600.jpg | 1 | 1 | 0.6880 | 174.88 |

首次加载耗时 2867.62 ms，后续同模型加载命中缓存，加载耗时为 0。首次推理还包含运行时初始化成本。以上耗时只描述本次测试，不作为严格性能基准。

六个任务均为 `succeeded`、`is_mock=false`，类别与对应样例类别一致，坐标在原图范围内。JSON 导出与任务详情一致；六张 PNG 均可解码且保持原图尺寸，鼠咬和毛刺的导出图另做了可视检查。

结果保留在页面“检测历史”中。原始报告、每张图的 JSON 和 PNG 位于 `backend/data/real-model-verification/`，汇总文件是 `summary.json`。该目录属于本地运行数据，不提交 Git。

这是接入与功能冒烟测试，没有计算完整测试集 mAP，也没有据此宣称模型准确率。数量一致不等同于所有框定位准确；模型质量评估应另行使用固定测试集。

## 直接使用

1. 刷新 http://127.0.0.1:5173 。
2. 在工作台勾选 **PCB YOLOv8s · 真实模型**，上传图片并开始检测。
3. 在“检测历史”查看这次六类测试结果。原来的两个演示模型仍标注“模拟”，旧模拟历史不会自动变为真实结果。

重复验证命令（服务启动后，在 backend 目录运行）：

```powershell
uv run --extra yolo python scripts/verify_live.py
```

浏览器截图验收仍未进行；本次额外完成了真实 HTTP 全流程和导出图片的本地可视检查。
