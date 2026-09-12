# 模型目录（2026-09-12）

`backend/models.json` 统一使用多行 JSON，字段顺序为 id、name、version、author、description、adapter、device、weights；按 v8、v11、v12、v26 排列，默认仅包含四个真实模型。

| 模型                | 作者   | 固定权重文件                           |
| ------------------- | ------ | -------------------------------------- |
| YOLOv8s             | 程嘉标 | `pcb-yolov8s-20260911.pt`            |
| YOLOv11n            | 林天佑 | `pcb-yolov11n-20260908.pt`           |
| YOLOv12n            | 潘景琪 | `pcb-yolov12n-20260910.pt`           |
| YOLOv26n（YOLO26n） | 林朴   | `pcb-yolov26n-20260911.pt`（待交付） |

文件统一位于 `backend/weights/`，采用 `pcb-模型名-YYYYMMDD.pt`；版本日期表示来源版本，不随重命名改变。保留已有模型 ID 以兼容接口调用，历史结果保留原快照。旧文件保存在本机 `weights/archive/`，不参与注册、不提交 Git。

YOLOv8s 使用最新完成的 `runs/clean-v2/yolov8s_scale02_seed0-3/weights/best.pt` 固定副本。该次训练完成 30 轮，以本次训练的最佳 checkpoint 为选择标准，并非宣称跨实验或测试集最优。训练目录未修改。

YOLOv11、YOLOv12 使用本机已有交付文件，复制并校验后统一名称。v11 SHA-256 与历史清单一致，旧清单文件大小已更正。林朴同学的 YOLO26n 权重未在本机找到，不以其他 YOLO26s 或预训练权重替代。校验值及来源见 `backend/weights.manifest.json`，其中 source 相对仓库根目录，file 相对 backend 目录。

本说明取代旧分支集成记录中的模型名称、路径及演示模型配置描述。模拟适配器仍用于自动测试，但默认接口和页面不返回演示模型。无权重时基础 API 可启动，实际检测返回模型未就绪。

2026-09-12 在当前后端环境通过 FastAPI TestClient 执行 CPU 真实推理：v8、v11、v12 对同一张本地 PCB 验证图片均返回 succeeded、is_mock=false，各检出 2 个缺陷。证据保存在被忽略的 `backend/data/model-verification-20260912/`。这仅是单图 API 冒烟验证，不是完整验收或准确率评估。后端 14 项回归测试通过。
