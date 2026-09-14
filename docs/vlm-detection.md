# VLM 零样本检测

上传图片后选择“Qwen VLM · 零样本检测”，可以单独使用，也可与 YOLO 在同一任务中独立对比。VLM 只接收原图与固定类别定义、输出格式要求，不接收文件名、人工标注、YOLO 结果或缺陷数量。不训练模型参数，属于零样本检测。

## 配置

在仓库根目录 `.env` 或 `backend/.env` 设置 `QWEN_API_KEY`（也支持 `DASHSCOPE_API_KEY`）。同名环境变量优先于文件，后端文件优先于根目录文件。密钥只在后端读取，`.env` 已忽略，不会返回前端。可以从 `backend/.env.example` 复制模板。

```powershell
cd backend
uv sync --locked --python 3.11 --extra yolo --extra qwen
$env:PCB_MODELS_CONFIG = (Resolve-Path models.json).Path
uv run --extra yolo --extra qwen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

模型配置为 `adapter:"vlm"`、`provider_model:"qwen3-vl-plus"`、`device:"cloud"`。修改云端模型时同步更新配置版本，并重新验证坐标协议。云端别名可能更新，不能把别名当成固定权重哈希。当前使用 DashScope SDK 默认服务地域；密钥必须适用于该服务。

选择 VLM 后，界面会提示原图将发送至阿里云并产生调用费用。没有密钥或 SDK 时 VLM 不可选，基础 API 仍可启动。

## 数据链路与持久化

1. `POST /api/v1/images` 保存 EXIF 校正后的 RGB PNG 和图片元信息。
2. `POST /api/v1/inferences` 接收图片 ID、模型 ID 列表和阈值，返回 202、任务 ID。前端不提供任何预测。
3. 单工作线程读取后端图片，调用 VLM。请求包含 PNG Base64 和 `pcb-zero-shot-v1` 提示词。
4. 校验结构化输出，转换坐标，按自评分阈值过滤；通过现有 `update_result()` 事务写入 SQLite `jobs.results` JSON 字段。
5. 前端轮询任务，绘制检测框并显示已保存说明；刷新、重启后从数据库读取，不再次调用云端。历史、JSON/PNG 导出和删除复用现有接口。

数据库默认 `backend/data/history.sqlite3`，可由 `PCB_DATA_DIR` 改写。无需迁移或清空旧数据库：只为 results JSON 新增可选字段，旧记录仍可读取。图片清理按任务引用计数执行，其他任务仍引用图片时不会删除图片。未完成任务在服务重启后标记失败，不自动重复付费调用。

保存内容：模型名称、方法、配置版本、云端模型名，`detections` 中的类别、自评分、原图像素坐标、观察依据，以及 `vlm` 中的判断、中文总结、提示词版本、归一化坐标协议、候选/保留数量、原始响应文本、请求 ID。密钥与请求图片 Base64 不进入结果字段。原始输出在 JSON 导出中可追溯，前端只显示结构化说明。

## 判断与坐标

- `suspected_defects`：有可定位候选，仍需复核。
- `no_visible_defects`：没有发现可见缺陷，不等同于产品合格。
- `uncertain`：无法确定，可有疑似候选，也可没有框。

VLM 返回 0～1000 的归一化 xyxy，后端按 `x/1000*原图宽`、`y/1000*原图高` 转成统一原图像素坐标。拒绝未知类别、NaN、越界或倒置框、缺失字段、判断与候选冲突、截断响应和无效 JSON，不将失败转换成无缺陷。所有候选都先校验，再执行阈值过滤。

模型自评分不是校准概率，不能直接与 YOLO 置信度比较。若阈值过滤掉全部候选，仍保留原始“疑似缺陷/无法确定”判断与候选数量，不会显示“检测合格”。每次请求限制 100 个候选、8192 个输出 token、60 秒 SDK 请求超时；PNG Base64 超过 9 MB 时任务失败，不隐式降采样微小缺陷。云端使用独立队列和两个调用线程，不占 YOLO 槽位；仍须单个 Uvicorn worker。默认每日 100 次尝试，额度持久化、失败计入，不自动重试。详见 [演示部署](demo-deployment.md)。

## 验证

自动测试使用替代服务，覆盖坐标缩放、EXIF 方向、空结果/不确定、阈值、无效输出、服务失败、数据库关闭后重开、历史、导出及图片引用清理。

2026-09-12 本地验证：后端 27 项测试、前端 3 项组件测试及生产构建通过，旧历史 JSON 导出与新接口响应一致。这些自动测试不代表云端效果验收。

同日经用户授权尝试真实云端验证：默认 PNG 请求遇到 `SSLError/SSLEOFError`；诊断时改用同一图片的原始 JPEG 编码，云端返回 HTTP 401，未取得有效推理结果。JPEG 仅用于隔离传输问题的诊断，正式适配器仍使用 PNG。需要核对密钥有效性及服务地域后重新验证。失败任务已入库，不能据此宣称真实检测或成功结果恢复验证通过。鉴权失败的本地证据为 `backend/data/vlm-verification/fbc26d47d6f54e71ac378fa19a4a89c6/result.json`。

更新密钥后的真实验证已返回成功（记录时间 2026-09-12 22:33，北京时间）：模型 `qwen3-vl-plus`，请求 ID `528d9d2a-4148-98a9-874b-4b85b1c5c566`，推理耗时约 7.62 秒。判断为 `uncertain`，返回 0 个候选、0 个定位框；数据库重开后的详情和 JSON 导出均与原结果一致。证据为 `backend/data/vlm-verification/52adb322cdf0467c86a2cce04734a313/result.json`，使用隔离验证数据库，不会出现在默认工作台历史中。本图数据集标注有一处毛刺，本次未定位出来，只证明调用与持久化链路成功。

该次历史运行产生 HTTPS 未校验警告，当时的补丁将 SDK session 的 `verify` 设为 False，不能作为启用证书校验的连接验收。现已移除该补丁，使用各调用线程独立的 session 和默认 TLS 验证；目标服务器仍须使用真实样例重新验收，代理环境配置可信 CA。

经授权后可执行真实云端单图验证（会发送图片并产生费用；先自备 `backend/weights/sample_pcb.jpg`，以下代码块从仓库根目录开始）：

```powershell
cd backend
uv run --extra yolo --extra qwen python scripts/verify_vlm.py --image weights/sample_pcb.jpg
```

脚本使用隔离数据目录 `backend/data/vlm-verification/<随机ID>/`，校验真实结果与数据库重开后的结果一致。单图成功仅验证接口与持久化，不代表定位准确率。需独立的正常/缺陷样本集评估误报、漏检和 IoU，不能用 YOLO 输出充当真值。

参考：[阿里云视觉理解与定位接口](https://help.aliyun.com/zh/model-studio/vision)。
