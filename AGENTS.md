# 团队协作约定

## 项目边界

本仓库共享 PCB 推理展示系统。前端在 `frontend/`，FastAPI 服务在 `backend/`，说明在 `docs/`。根目录可能存在本机训练工程，不属于系统提交范围。

- 默认只修改前后端、对应测试及文档。不得擅自修改、迁移或停止成员的训练任务。
- 不提交训练脚本、数据集、训练结果、日志、权重、虚拟环境、node_modules、运行数据库或导出图片。
- 保留用户已有改动。提交前查看状态，按明确路径暂存，禁止用 `git add .` 混入训练文件。
- 用户要求提交时先完成验证、检查暂存差异；仅在明确要求时推送远端或创建 PR。

## 技术与接口

- 前端为 React、TypeScript、Vite、Ant Design、TanStack Query，使用中文界面。
- 后端为 Python 3.11、FastAPI、Pydantic、SQLAlchemy、SQLite，使用 uv 和锁文件管理依赖。
- API 前缀为 `/api/v1`。保持已有接口兼容；类型变更同步后端 OpenAPI、前端类型和接入文档。
- 检测坐标是 EXIF 方向校正后的原图像素 xyxy；类别字典以 `backend/app/schemas.py` 为准。
- 模拟结果必须持续标注 `is_mock`，不得用模拟结果证明真实推理或模型准确率。

## 模型接入

- 模型代码封装在适配器，提供 `load()`、`predict(image, confidence)`、`unload()`。
- 可选框架延迟导入。缺少真实权重或推理依赖时，基础 API 与模拟流程必须能启动。
- 适配器负责类别映射、阈值过滤、预处理、后处理和坐标还原；不能假设成员的类别编号一致。
- 权重由配置引用固定版本副本，不依赖持续写入的训练 checkpoint，不通过网页接收任意代码或权重执行。
- 当前默认 CPU、单 worker、串行推理与单模型缓存。不要未经设计扩展为共享同一数据库和队列的多进程服务。
- 真实接入需在目标环境通过真实样例的 API 验证。说明版本与测试限制，不能将模拟测试或旧环境通过当作目标环境验收。

## 开发与提交检查

后端基础环境：在 `backend/` 执行 `uv sync --locked` 和 `uv run pytest -q`。已启用真实推理时使用 `uv run --extra yolo pytest -q`，避免移除推理依赖。

前端：在 `frontend/` 执行 `npm ci`、`npm test`、`npm run build`。按改动范围检查；修改依赖时更新对应锁文件。

接入参考 `docs/model-integration.md`。真实验证脚本在 `backend/scripts/`，权重和样例由本地提供，生成证据留在被忽略的数据目录。

提交前执行 `git diff --check`，核对 `git diff --cached --name-only` 和暂存内容，确保没有训练文件、模型二进制或本地运行数据。保持 README 的全新克隆、无权重模拟启动路径可用。
