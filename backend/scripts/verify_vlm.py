"""Run one real, paid VLM API request and verify persistence in isolated storage."""
import argparse
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1]/'models.json')
    parser.add_argument('--model', default='pcb-qwen-vlm')
    parser.add_argument('--local-model', action='append', default=[], help='Also run a real YOLO model to observe independent scheduling')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'data/vlm-verification')
    args = parser.parse_args()
    output = args.output/uuid4().hex
    output.mkdir(parents=True)
    with TestClient(create_app(output/'api-data', args.config)) as client:
        catalog = client.get('/api/v1/models').json()
        model = next(m for m in catalog if m['id'] == args.model)
        if not model['available'] or model['method'] != 'vlm':
            raise RuntimeError(model['availability_message'])
        for model_id in args.local_model:
            local = next(m for m in catalog if m['id'] == model_id)
            if not local['available'] or local['method'] != 'yolo':
                raise RuntimeError(f'Not an available YOLO model: {model_id}')
        r = client.post('/api/v1/images', files={'file':('sample.jpg',args.image.read_bytes(),'image/jpeg')})
        r.raise_for_status()
        started = time.monotonic()
        completion_seconds = {}
        r = client.post('/api/v1/inferences',json={'image_id':r.json()['id'],'model_ids':[args.model, *args.local_model],'confidence':.25})
        r.raise_for_status()
        job_id = r.json()['id']
        deadline = time.monotonic()+300
        while True:
            job = client.get(f'/api/v1/inferences/{job_id}').json()
            for result in job['results']:
                if result['status'] in {'succeeded', 'failed'}:
                    completion_seconds.setdefault(result['model']['id'], round(time.monotonic()-started, 3))
            if job['status'] in {'succeeded','failed','partial'}:
                break
            if time.monotonic() > deadline:
                raise TimeoutError('VLM verification timed out')
            time.sleep(.25)
        (output/'result.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
        (output/'completion-seconds.json').write_text(json.dumps(completion_seconds, indent=2), encoding='utf-8')
        if job['status'] != 'succeeded':
            raise RuntimeError(f'VLM task failed; see {output / "result.json"}')
        assert job['results'][0]['is_mock'] is False and job['results'][0]['vlm']
        assert all(not result['is_mock'] for result in job['results'])
    with TestClient(create_app(output/'api-data',args.config)) as client:
        assert client.get(f'/api/v1/inferences/{job_id}').json() == job
        assert client.get(f'/api/v1/inferences/{job_id}/export').json() == job
    print(json.dumps({'status':'succeeded','persisted_after_restart':True,
        'assessment':job['results'][0]['vlm']['assessment'],
        'detections':len(job['results'][0]['detections']), 'completion_seconds':completion_seconds,
        'evidence':str(output/'result.json')}))


if __name__ == '__main__':
    main()
