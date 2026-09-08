"""Exercise a real registered model via HTTP, with one test image per PCB class."""
import argparse
import io
import json
import time
from pathlib import Path

import httpx
from PIL import Image

CLASSES = ['mouse_bite', 'spur', 'missing_hole', 'short', 'open_circuit', 'spurious_copper']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:5173/api/v1')
    parser.add_argument('--model', default='pcb-yolov8s-baseline')
    parser.add_argument('--dataset', type=Path, default=Path('../pcb-defect-dataset/test'))
    parser.add_argument('--output', type=Path, default=Path('data/real-model-verification'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    samples = {}
    for label in sorted((args.dataset / 'labels').glob('*.txt')):
        rows = [line.split() for line in label.read_text().splitlines() if line.strip()]
        for row in rows:
            class_id = int(row[0])
            if class_id in samples:
                continue
            image = next((p for suffix in ('.jpg', '.png', '.jpeg')
                          if (p := args.dataset / 'images' / (label.stem + suffix)).is_file()), None)
            if image:
                samples[class_id] = (image, rows)
        if len(samples) == 6:
            break
    assert len(samples) == 6, 'Dataset must contain all six classes'
    evidence = []
    with httpx.Client(base_url=args.url, timeout=60) as client:
        response = client.get('/models')
        response.raise_for_status()
        model = next(m for m in response.json() if m['id'] == args.model)
        assert model['available'] and not model['is_mock'], model
        for class_id in range(6):
            path, rows = samples[class_id]
            response = client.post('/images', files={'file': (path.name, path.read_bytes(), 'image/jpeg')})
            response.raise_for_status()
            uploaded = response.json()
            response = client.post('/inferences', json={
                'image_id': uploaded['id'], 'model_ids': [args.model], 'confidence': .25})
            response.raise_for_status()
            job_id = response.json()['id']
            deadline = time.monotonic() + 300
            while True:
                response = client.get(f'/inferences/{job_id}')
                response.raise_for_status()
                job = response.json()
                if job['status'] in {'succeeded', 'failed', 'partial'}:
                    break
                assert time.monotonic() < deadline, f'Task timeout: {job_id}'
                time.sleep(.25)
            assert job['status'] == 'succeeded', job
            result = job['results'][0]
            assert not result['is_mock'], result
            for detection in result['detections']:
                assert CLASSES[detection['class_id']] == detection['class_name']
                x1, y1, x2, y2 = detection['bbox_xyxy']
                assert 0 <= x1 < x2 <= uploaded['width'] and 0 <= y1 < y2 <= uploaded['height']
            response = client.get(f'/inferences/{job_id}/export')
            response.raise_for_status()
            assert response.json() == job
            (args.output / f'{class_id}-{CLASSES[class_id]}.json').write_text(response.text, encoding='utf-8')
            response = client.get(f'/inferences/{job_id}/export', params={'format':'png', 'model_id':args.model})
            response.raise_for_status()
            assert Image.open(io.BytesIO(response.content)).size == (uploaded['width'], uploaded['height'])
            (args.output / f'{class_id}-{CLASSES[class_id]}.png').write_bytes(response.content)
            summary = dict(class_name=CLASSES[class_id], image=path.name, job_id=job_id,
                           ground_truth_count=len(rows), detection_count=len(result['detections']),
                           predicted_classes=[d['class_name'] for d in result['detections']],
                           confidences=[round(d['confidence'], 4) for d in result['detections']],
                           load_ms=result['load_ms'], inference_ms=result['inference_ms'])
            evidence.append(summary)
            print(json.dumps(summary), flush=True)
    (args.output / 'summary.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
    print('PASS: six real-model tasks, canonical classes, original coordinates, JSON and PNG exports')


if __name__ == '__main__':
    main()
