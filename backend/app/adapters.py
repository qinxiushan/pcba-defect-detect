"""Model-only code: no web or database dependencies; Torch is imported lazily."""
import gc
import hashlib
import importlib
import os
import sys
from pathlib import Path
from typing import Protocol
from PIL import Image
from .schemas import CLASS_NAMES, Detection, ModelConfig


class Adapter(Protocol):
    def load(self) -> None: ...
    def predict(self, image: Image.Image, confidence: float) -> list[Detection]: ...
    def unload(self) -> None: ...


class MockAdapter:
    def __init__(self, config: ModelConfig):
        self.config = config

    def load(self):
        pass

    def predict(self, image, confidence):
        digest = hashlib.sha256(image.tobytes() + str(self.config.seed).encode()).digest()
        w, h = image.size
        boxes = []
        for i in range(3):
            score = round(0.55 + digest[i] / 255 * 0.43, 3)
            if score < confidence:
                continue
            cls = (digest[i + 3] + self.config.seed) % 6
            x, y = digest[i + 6] / 255 * .7, digest[i + 9] / 255 * .7
            boxes.append(Detection(class_id=cls, class_name=CLASS_NAMES[cls], confidence=score,
                                   bbox_xyxy=(x*w, y*h, (x+.12)*w, (y+.1)*h)))
        return boxes

    def unload(self):
        pass


class YoloAdapter:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.model = None

    def load(self):
        if not self.config.weights or not Path(self.config.weights).is_file():
            raise ValueError('权重文件不存在')
        import torch
        torch.set_num_threads(max(1, int(os.getenv('PCB_TORCH_THREADS', '2'))))
        if self.config.register_hook:
            module, function = self.config.register_hook.split(':')
            getattr(importlib.import_module(module), function)()
        from ultralytics import YOLO
        self.model = YOLO(self.config.weights)

    def predict(self, image, confidence):
        result = self.model.predict(image, conf=confidence, device=self.config.device, verbose=False)[0]
        detections = []
        if result.boxes is None:
            return detections
        for box in result.boxes:
            original_id = int(box.cls.item())
            if self.config.class_map is not None:
                canonical = self.config.class_map[original_id]
            else:
                canonical = CLASS_NAMES.index(result.names[original_id])
            coords = box.xyxy[0].tolist()
            coords = [max(0, min(v, image.width if i % 2 == 0 else image.height)) for i, v in enumerate(coords)]
            if coords[0] >= coords[2] or coords[1] >= coords[3]:
                continue
            detections.append(Detection(class_id=canonical, class_name=CLASS_NAMES[canonical],
                                        confidence=float(box.conf.item()), bbox_xyxy=coords))
        return detections

    def unload(self):
        self.model = None
        gc.collect()
        torch = sys.modules.get('torch')
        if torch is not None and hasattr(torch, 'cuda') and torch.cuda.is_available():
            torch.cuda.empty_cache()


def create_adapter(config: ModelConfig) -> Adapter:
    return {'mock': MockAdapter, 'yolo': YoloAdapter}[config.adapter](config)
