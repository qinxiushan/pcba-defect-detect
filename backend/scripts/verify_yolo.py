"""Smoke-test a local PCB checkpoint with the exact production adapter, on CPU."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageOps
from app.adapters import YoloAdapter
from app.schemas import ModelConfig

parser = argparse.ArgumentParser()
parser.add_argument('--weights', required=True)
parser.add_argument('--image', required=True)
args = parser.parse_args()
adapter = YoloAdapter(ModelConfig(id='smoke-test', name='PCB checkpoint', version='local',
                                  adapter='yolo', weights=args.weights, device='cpu'))
try:
    adapter.load()
    with Image.open(args.image) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    detections = adapter.predict(image, .25)
    print(json.dumps({'image_size': image.size, 'device': 'cpu', 'detections': [d.model_dump() for d in detections]}, ensure_ascii=False))
finally:
    adapter.unload()
