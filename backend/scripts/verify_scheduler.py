"""Real CPU model cache and five-client benchmark in isolated storage.

Run separately with --concurrency 1 and 2. Requires the yolo extra (including psutil).
No cloud requests are made by this script.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import threading
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psutil
from fastapi.testclient import TestClient
from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--concurrency', type=int, choices=[1, 2], required=True)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1]/'models.json')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'data/scheduler-verification')
    args = parser.parse_args()
    os.environ['PCB_LOCAL_CONCURRENCY'] = str(args.concurrency)
    output = args.output / uuid4().hex
    output.mkdir(parents=True)
    process = psutil.Process()
    stop = threading.Event()
    peak = [process.memory_info().rss]
    def memory():
        while not stop.wait(.05):
            peak[0] = max(peak[0], process.memory_info().rss)
    monitor = threading.Thread(target=memory)
    monitor.start()
    report = dict(concurrency=args.concurrency, platform=sys.platform, cpu_count=os.cpu_count(),
                  torch_threads=os.getenv('PCB_TORCH_THREADS', '2'), rounds=[], clients=[])
    try:
        with TestClient(create_app(output/'api-data', args.config)) as client:
            models = [m for m in client.get('/api/v1/models').json() if m['method'] == 'yolo' and m['available']]
            if len(models) < 2:
                raise RuntimeError('At least two available real YOLO models are required')
            report['models'] = models
            response = client.post('/api/v1/images', files={'file': ('sample.jpg', args.image.read_bytes())})
            response.raise_for_status()
            image_id = response.json()['id']
            def run():
                started = time.perf_counter()
                response = client.post('/api/v1/inferences', json=dict(image_id=image_id, model_ids=[m['id'] for m in models]))
                response.raise_for_status()
                job_id = response.json()['id']
                observed_start = {}
                while time.perf_counter() - started < 300:
                    job = client.get(f'/api/v1/inferences/{job_id}').json()
                    elapsed = time.perf_counter() - started
                    for r in job['results']:
                        if r['status'] != 'queued':
                            observed_start.setdefault(r['model']['id'], round(elapsed, 3))
                    if job['status'] in ('succeeded', 'partial', 'failed'):
                        record = dict(elapsed_seconds=round(elapsed, 3), observed_queue_seconds=observed_start, job=job)
                        (output/f'{job_id}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
                        assert job['status'] == 'succeeded' and all(not r['is_mock'] for r in job['results'])
                        return record
                    time.sleep(.02)
                raise TimeoutError(job_id)
            report['rounds'] = [run(), run()]
            assert all(r['load_ms'] == 0 for r in report['rounds'][1]['job']['results'])
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=5) as pool:
                report['clients'] = list(pool.map(lambda _: run(), range(5)))
            report['five_client_seconds'] = round(time.perf_counter()-started, 3)
            report['status'] = 'succeeded'
    finally:
        stop.set()
        monitor.join()
        report['peak_rss_mb'] = round(peak[0]/1024**2, 1)
        (output/'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(dict(evidence=str(output/'summary.json'), status=report.get('status', 'failed'),
                             peak_rss_mb=report['peak_rss_mb'], five_client_seconds=report.get('five_client_seconds'))))


if __name__ == '__main__':
    main()
