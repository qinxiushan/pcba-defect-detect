from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
DATA_CONFIG = ROOT / "pcb-defect-dataset" / "data.yaml"


def main() -> None:
    model = YOLO("yolo26n.pt")
    model.train(
        data=str(DATA_CONFIG),
        epochs=100,
        imgsz=640,
        batch=-1,
        seed=42,
            workers=0,
        project=str(ROOT / "runs"),
        device=0,
        name="yolo26n_pcb_gpu_100ep",
    )


if __name__ == "__main__":
    main()