# 模型常驻与独立调度验证（2026-09-14）

本轮在本地 Windows CPU 环境验证，20 个逻辑 CPU，Torch CPU 线程数 2。版本：Ultralytics 8.4.143、Torch 2.8.0+cpu、DashScope 1.27.5。不是目标 Linux 服务器验收，未包含公网、Nginx 或 HTTPS 代理延迟。

## 真实 YOLO

使用固定版本 YOLOv8s、YOLOv11n、YOLOv12n 三份权重；YOLOv26n 权重缺失，未参与。图片为此前授权的 600×600 PCB 样例 `.cache/vlm-demo/sample.jpg`。通过 FastAPI TestClient 上传图片、提交任务、轮询真实推理结果，未使用模拟适配器。

| 指标 | 本地并发 1 | 本地并发 2 |
| --- | ---: | ---: |
| 第二轮三模型总耗时 | 0.615 秒 | 0.334 秒 |
| 第二轮每个模型加载耗时 | 全部 0 | 全部 0 |
| 五客户端总耗时（共 15 次模型推理） | 4.365 秒 | 2.513 秒 |
| 进程 RSS 采样峰值 | 634.7 MB | 641.2 MB |

两种配置所有任务均成功。当前机器这一次测量中，并发 2 总耗时缩短约 42%；没有重复多轮统计，操作系统文件缓存和后台负载可能影响结果，不将其推广为服务器容量保证。首轮包含框架初始化、权重读取和模型加载，不用两次进程的首轮时间直接比较并发性能。

本地证据（忽略目录，不提交）：

- `backend/data/scheduler-verification/5e9a13a58e154cc9940af08086fa373d/summary.json`
- `backend/data/scheduler-verification/911061cac7ad48d3aeb0f34c0b3d8bbe/summary.json`

## 真实 VLM

移除关闭 TLS 校验的补丁后，使用独立 requests session、默认 TLS 验证和禁止连接错误自动重试的实现，真实 Qwen 调用成功，重启后查询和 JSON 导出与原记录一致。

证据：`backend/data/vlm-verification/14d41b13fbda4dd492daf1c1a845b374/result.json`。结果为 `uncertain`、0 个定位框；链路成功不代表定位准确率通过。

另一次同一任务同时选择真实 YOLOv8s 和 Qwen：YOLO 在约 4.188 秒完成，VLM 在约 8.281 秒完成（包含首次加载，250ms 轮询观察）；证明本地结果不必等待云端结束。两项均成功，重启后查询和导出一致。证据位于 `backend/data/vlm-verification/b764da43c83a412a91f8c8cf1b0ae58b/`，含 `result.json` 与 `completion-seconds.json`。

## 功能与部署边界

后端测试覆盖模型线程归属、常驻缓存、不同模型重叠执行、同模型串行、云端不阻塞本地、并行结果无覆盖、部分失败、队列满、删除历史和重启不重置云端额度、TLS 默认校验及无自动连接重试。前端测试覆盖本地结果完成后云端仍在排队的展示。

Nginx 与 systemd 提供配置模板；本机没有正在运行的 Docker 服务，也没有 Nginx 可执行文件，未执行真实反向代理认证测试。目标服务器仍需按 [演示部署](demo-deployment.md) 验证证书、共享密码覆盖网页/API/图片、服务用户权限和五客户端容量。
