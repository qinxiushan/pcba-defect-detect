# 团队模型接入契约

前端只依赖统一业务协议，每个模型负责把自己的输出转换为统一检测结果。第一版支持矩形框目标检测，不支持分割掩码和旋转框。

## 成员交付清单

1. 固定版本权重和模型名称、版本、作者、描述；建议记录权重 SHA-256。
2. 推理所需网络定义、自定义模块、加载入口和完整依赖版本；训练时临时 monkey patch 的方法不一定能随 checkpoint 恢复，需独立验证加载。
3. 模型自己的类别表及其与下表的映射。
4. 预处理、输入尺寸、RGB/BGR、归一化、后处理/NMS 参数和坐标还原说明。
5. 至少一张 PCB 样例图、对应真实推理 JSON，以及适配器加载和执行命令。无目标时返回空列表。

| 系统 ID | class_name | 中文 |
|---|---|---|
| 0 | mouse_bite | 鼠咬 |
| 1 | spur | 毛刺 |
| 2 | missing_hole | 缺失孔 |
| 3 | short | 短路 |
| 4 | open_circuit | 开路 |
| 5 | spurious_copper | 杂铜 |

不要通过模型 ID 推测类别，也不要直接沿用未核对的训练类别编号。

## 注册一个 YOLO 模型

在 `backend/models.json` 数组中添加（以下路径和版本仅作示例，按实际交付替换）：

```json
{
  "id": "member-li-v1",
  "name": "李同学 · 改进 YOLO",
  "version": "2026-09-08-v1",
  "author": "李同学",
  "description": "带注意力模块的 PCB 检测模型",
  "adapter": "yolo",
  "device": "cpu",
  "weights": "../weights/member-li-v1/best.pt",
  "register": "member_models.register:register_modules",
  "class_map": {"0": 3, "1": 0, "2": 1, "3": 2, "4": 4, "5": 5}
}
```

`class_map` 是 **模型 ID → 系统 ID**；此例假设模型的第 0 类是 short。如果 checkpoint 的类名已经是系统的英文名，可省略映射，让适配器按类名匹配。未知类别或缺失映射会让该模型任务失败，不能静默改成其他类别。

`register` 可省略。需要时提供可导入的 `模块:函数`，函数无参数，在 YOLO 加载权重前执行。将成员推理代码作为可安装包加入后端依赖，或将模块置于后端的 Python 导入路径。不要调用会启动训练的入口。该配置仅由开发者编辑，网页不会接受任意模块名或权重上传。

注册后重启服务。模型目录的“待首次加载验证”表示权重和依赖存在，不表示 checkpoint 已经成功加载；真实请求完成才算接入成功。加载失败详情在后端日志中，页面显示通用错误且其他模型继续执行。

## 新适配器模板

在后端模型适配器模块中实现：

```python
from PIL import Image
from app.schemas import Detection, ModelConfig

class MemberAdapter:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.model = None

    def load(self) -> None:
        # 在此导入框架并加载权重；不要在模块顶层导入 Torch。
        # self.model = ...
        raise NotImplementedError("填入成员模型加载代码")

    def predict(self, image: Image.Image, confidence: float) -> list[Detection]:
        # image 已校正 EXIF 方向，是原尺寸 RGB 图。
        # 完成预处理、推理、后处理、阈值过滤与原图坐标还原。
        # 使用 Detection(class_id=..., class_name=..., confidence=...,
        #                bbox_xyxy=(x1, y1, x2, y2)) 返回每个框。
        raise NotImplementedError("填入成员推理代码")

    def unload(self) -> None:
        self.model = None
        # 释放框架缓存和设备资源；load 部分失败时也必须能安全调用。
```

在 `ModelConfig.adapter` 的 Literal 中添加适配器名称，并在 `create_adapter` 映射和 `Service.availability` 中增加对应创建逻辑及依赖/权重检查。无需修改任务 API、数据库或 React。对复杂配置，可扩展模型配置类型，但不要向业务请求暴露模型特有内部参数。

契约要求：框坐标为校正方向后的原图像素坐标，`0 ≤ x1 < x2 ≤ width`、`0 ≤ y1 < y2 ≤ height`；置信度为 0～1，不能出现 NaN 或无穷值；class_name 与系统 ID 一致。适配器负责反归一化及去除 letterbox 填充。YOLO 适配器使用 Ultralytics 已恢复至原图的 `boxes.xyxy`，不要再缩放一次。

加载和 predict 都在专用串行线程执行，不会占用 FastAPI 的异步事件循环。仅缓存一个模型；再次使用同一模型时加载耗时为 0。无法共存的框架可以以后用远程适配器实现同一契约，第一版不要求成员维护 HTTP 服务。

## 业务调用示例

```python
import time
import httpx

with httpx.Client(base_url="http://127.0.0.1:8000/api/v1") as client:
    with open("pcb.png", "rb") as file:
        response = client.post("/images", files={"file": file})
    response.raise_for_status()
    image = response.json()
    response = client.post("/inferences", json={
        "image_id": image["id"],
        "model_ids": ["demo-a", "demo-b"],
        "confidence": 0.25
    })
    response.raise_for_status()
    task_id = response.json()["id"]
    while True:
        response = client.get(f"/inferences/{task_id}")
        response.raise_for_status()
        task = response.json()
        if task["status"] in {"succeeded", "failed", "partial"}:
            break
        time.sleep(1)
    print(task)
```

任务返回 `image`（ID、尺寸、URL）、`confidence`、`created_at`、`results`。每个结果包含模型快照、`is_mock`、状态、检测列表、`load_ms`、`inference_ms` 和错误消息。完整类型在 FastAPI `/docs` 和 `/openapi.json` 可查看。JSON 和 PNG 导出使用同一持久化结果，不重新运行模型；PNG 模拟结果带 `SIMULATED` 标记。

## 接入验收

- 在新进程独立加载固定权重，使用 `scripts/verify_yolo.py` 或成员自己的等价脚本跑真实 PCB 图。
- 验证类别映射、空检测、极小目标、非正方形图片和边界坐标。
- 同图与一个模拟模型一起提交；真实结果不带模拟标记，模拟结果始终带标记。
- 验证依赖缺失或权重损坏不会阻止 API 启动，任务失败有日志可追踪。
- 同一权重版本使用不可变配置；模型更新创建新版本，旧历史保持原始快照。
- 将验证图片、权重版本和运行环境记录下来；模拟测试通过不等于真实模型通过，也不等于模型准确率达标。
