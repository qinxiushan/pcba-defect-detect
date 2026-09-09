"""接入验收：边界用例 + 同图与 mock 模型对比提交（符合 model-integration.md 验收清单）。"""
import io
import json
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageOps

# ---- 准备 ----
BACKEND = "http://127.0.0.1:8000/api/v1"
MODEL_ID = "member-yolov11"
SAMPLE_IMG = Path(__file__).resolve().parent / "weights" / "sample_pcb.jpg"

# ---- 辅助 ----
def upload_image(client, img_path):
    with open(img_path, "rb") as f:
        r = client.post("/images", files={"file": (Path(img_path).name, f, "image/jpeg")})
    r.raise_for_status()
    return r.json()

def submit_and_wait(client, image_id, model_ids, confidence=0.25):
    r = client.post("/inferences", json={
        "image_id": image_id,
        "model_ids": model_ids,
        "confidence": confidence,
    })
    r.raise_for_status()
    job_id = r.json()["id"]
    for _ in range(60):
        task = client.get(f"/inferences/{job_id}").json()
        if task["status"] in ("succeeded", "failed", "partial"):
            return task
        time.sleep(1)
    raise TimeoutError("推理任务超时")

def check_box(d, w, h):
    x1, y1, x2, y2 = d["bbox_xyxy"]
    assert 0 <= x1 < x2 <= w, f"x: {x1}~{x2} vs width {w}"
    assert 0 <= y1 < y2 <= h, f"y: {y1}~{y2} vs height {h}"
    assert 0 <= d["confidence"] <= 1, f"conf={d['confidence']}"
    assert d["class_name"] in ["mouse_bite","spur","missing_hole","short","open_circuit","spurious_copper"]

# ---- 测试 ----
results_log = []
with httpx.Client(base_url=BACKEND, timeout=120) as c:
    # 1) 健康检查
    h = c.get("/health").json()
    assert h["status"] == "ok"
    print("[1] 后端健康检查: OK")

    # 2) 同图与 mock 模型对比提交
    img = upload_image(c, SAMPLE_IMG)
    task = submit_and_wait(c, img["id"], [MODEL_ID, "demo-a"], 0.25)
    real_res = next(r for r in task["results"] if r["model"]["id"] == MODEL_ID)
    mock_res = next(r for r in task["results"] if r["model"]["id"] == "demo-a")
    assert real_res["status"] == "succeeded", f"真实模型失败: {real_res.get('error')}"
    assert real_res["is_mock"] is False, "真实模型不应带 mock 标记"
    assert mock_res["is_mock"] is True, "模拟模型必须带 mock 标记"
    assert len(real_res["detections"]) > 0, "真实模型应检出缺陷"
    for d in real_res["detections"]:
        check_box(d, img["width"], img["height"])
    print(f"[2] 同图对比: 真实={len(real_res['detections'])}个缺陷 is_mock=False | mock={len(mock_res['detections'])}个 is_mock=True")
    results_log.append({"test": "mock_comparison", "real": real_res, "mock_is_mock": mock_res["is_mock"]})

    # 3) 高置信度阈值 → 空检测
    task_empty = submit_and_wait(c, img["id"], [MODEL_ID], confidence=0.99)
    empty_res = task_empty["results"][0]
    assert empty_res["status"] == "succeeded"
    # 空列表是合法结果
    print(f"[3] 高阈值(0.99)空检测: {len(empty_res['detections'])}个缺陷（合法）")
    results_log.append({"test": "empty_detection", "detections": len(empty_res["detections"])})

    # 4) 非正方形图片（裁剪为 500x300）
    with Image.open(SAMPLE_IMG) as src:
        non_square = ImageOps.exif_transpose(src).convert("RGB").crop((0, 0, 500, 300))
        buf = io.BytesIO()
        non_square.save(buf, format="JPEG")
        r = c.post("/images", files={"file": ("non_square.jpg", buf.getvalue(), "image/jpeg")})
        r.raise_for_status()
        ns_img = r.json()
    assert ns_img["width"] == 500 and ns_img["height"] == 300
    task_ns = submit_and_wait(c, ns_img["id"], [MODEL_ID], 0.25)
    ns_res = task_ns["results"][0]
    assert ns_res["status"] == "succeeded"
    for d in ns_res["detections"]:
        check_box(d, 500, 300)
    print(f"[4] 非正方形图 500x300: {len(ns_res['detections'])}个缺陷，坐标全部合法")
    results_log.append({"test": "non_square", "size": [500, 300], "detections": ns_res["detections"]})

    # 5) 极小目标验证（检查最小框面积）
    min_area = float("inf")
    for d in real_res["detections"]:
        x1,y1,x2,y2 = d["bbox_xyxy"]
        area = (x2-x1)*(y2-y1)
        if area < min_area:
            min_area = area
    print(f"[5] 最小检测框面积: {min_area:.1f} px²")
    results_log.append({"test": "min_target", "min_area_px": round(min_area,1)})

    # 6) 依赖缺失不阻止 API 启动（验证基线模型不可用但 API 正常）
    models = c.get("/models").json()
    baseline = next(m for m in models if m["id"] == "pcb-yolov8s-baseline")
    assert baseline["available"] is False, "基线模型权重缺失应不可用"
    assert baseline["availability_message"], "应有不可用原因"
    # 但 API 本身正常
    assert c.get("/health").json()["status"] == "ok"
    print(f"[6] 权重缺失不阻止 API: baseline available=False, API OK")
    results_log.append({"test": "missing_weights", "baseline_available": False, "api_ok": True})

# ---- 保存结果 ----
log_path = Path(__file__).resolve().parent / "weights" / "acceptance_results.json"
with open(log_path, "w", encoding="utf-8") as f:
    json.dump(results_log, f, ensure_ascii=False, indent=2, default=str)
print(f"\n验收结果已保存: {log_path}")
print("全部验收通过: 类别映射正确、空检测合法、非正方形图坐标合法、mock标记正确、权重缺失不阻止 API")
