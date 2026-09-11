# 分支集成记录（2026-09-11）

- `yolov11`：合并 `dffbb7f`，保留模型注册、权重清单、样例及成员交付记录。共享配置改为 CPU，成员文档中的 GPU 结果仅代表原环境。
- `yolov12`：合并 `bbdabbd`，接入 YOLOv12n 和可选 Qwen-VL 分析，补齐依赖锁文件、接口文档及自动测试。
- `YOLO26`：从 `77dc96b` 选择性集成模型注册；保留原 YOLOv8s 和演示模型。未合并训练脚本、数据配置、训练结果、根目录依赖及 README/.gitignore 改写，以遵守共享系统边界并保护本机训练文件。该分支没有整体合入主线。

## 权重交付与验收

所有模型默认 CPU。YOLOv11 和 YOLOv8s 的校验信息见 `backend/weights.manifest.json`。

YOLOv12 的固定权重路径为 `backend/weights/pcb-yolov12n-clean-20260910.pt`。YOLO26 的固定权重路径为 `backend/weights/pcb-yolo26n-baseline-20260911.pt`，应由成员从已完成的 50 轮训练中提供固定副本，不能直接引用持续写入的 `runs/` checkpoint。

YOLOv12、YOLO26 分支尚未提供权重校验清单；交付时需补充 SHA-256、文件大小、依赖版本及真实样例，并按 [接入契约](model-integration.md) 在目标环境验证。权重不提交 Git，本次没有操作训练目录或复制训练权重。

本次自动测试覆盖基础 API、模拟流程、分析接口与替代分析服务，不代表新增模型真实推理验收，也未调用 Qwen 云端服务。成员报告的准确率不能作为本次环境的验收证据。

验证结果：`uv sync --locked --extra yolo` 成功，后端 `uv run --extra yolo pytest -q` 14 项通过；前端 `npm ci`、3 项组件测试和 `npm run build` 通过。Windows 上默认进程池测试停滞，改为 Vitest 单 worker 线程池后通过。构建仍有大包提示；npm 报告 2 项 moderate 依赖漏洞，本次未进行依赖升级。
