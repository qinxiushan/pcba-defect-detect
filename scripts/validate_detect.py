from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
DATA_CONFIG = ROOT / "pcb-defect-dataset" / "data.yaml"
BEST_MODEL = ROOT / "runs" / "yolo26n_pcb_detect" / "weights" / "best.pt"


def main() -> None:
    model = YOLO(str(BEST_MODEL))
    metrics = model.val(data=str(DATA_CONFIG), imgsz=640)
    print(f"mAP50-95: {metrics.box.map:.4f}")
    print(f"mAP50: {metrics.box.map50:.4f}")


if __name__ == "__main__":
    main()