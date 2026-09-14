"""Single-process scheduling; each local model belongs to exactly one thread."""
import logging
import os
import queue
import sqlite3
import threading
import time
from contextlib import closing, nullcontext
from datetime import datetime, timezone

from PIL import Image
from sqlalchemy import select

from .db import JobRow
from .schemas import Detection

logger = logging.getLogger(__name__)
TERMINAL = {'succeeded', 'failed', 'partial'}


class QuotaExceeded(Exception):
    pass


def setting(name, default, minimum=1):
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f'{name} must be >= {minimum}')
    return value


class Scheduler:
    def start_scheduler(self):
        self.local_limit = setting('PCB_LOCAL_CONCURRENCY', 1)
        self.cloud_limit = setting('PCB_VLM_CONCURRENCY', 2)
        self.daily_limit = setting('PCB_VLM_DAILY_LIMIT', 100, 0)
        torch_threads = setting('PCB_TORCH_THREADS', 2)
        self.torch_error = False
        # Initialize global framework settings before any model worker starts.
        if any(m.adapter == 'yolo' and self.availability(m)[0] for m in self.models.values()):
            try:
                import torch
                torch.set_num_threads(torch_threads)
            except Exception:
                self.torch_error = True
                logger.exception('Optional YOLO runtime initialization failed')
        self.local_slots = threading.Semaphore(self.local_limit)
        self.stopping = threading.Event()
        self.local_queues = {m.id: queue.Queue() for m in self.models.values() if m.adapter != 'vlm'}
        self.cloud_queue = queue.Queue()
        self.threads = []
        # Separate accounting ledger survives history deletion; no history schema migration.
        with closing(sqlite3.connect(self.data / 'vlm-usage.sqlite3')) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS attempts (day TEXT NOT NULL, job_id TEXT NOT NULL, result_index INTEGER NOT NULL, PRIMARY KEY(job_id, result_index))')
        with self.Session.begin() as db:
            for job in db.scalars(select(JobRow).where(JobRow.status.not_in(TERMINAL))):
                job.results = [dict(r, status='failed', error='服务重启中断，请重新提交')
                               if r['status'] not in TERMINAL else r for r in job.results]
                job.status = self.aggregate(job.results)
        for model_id, tasks in self.local_queues.items():
            self.threads.append(threading.Thread(target=self.worker, args=(tasks, False), name=f'local-{model_id}', daemon=True))
        for i in range(self.cloud_limit):
            self.threads.append(threading.Thread(target=self.worker, args=(self.cloud_queue, True), name=f'vlm-{i}', daemon=True))
        for thread in self.threads:
            thread.start()

    @staticmethod
    def aggregate(results):
        if any(r['status'] not in TERMINAL for r in results):
            return 'running' if any(r['status'] != 'queued' for r in results) else 'queued'
        successes = sum(r['status'] == 'succeeded' for r in results)
        return 'succeeded' if successes == len(results) else 'partial' if successes else 'failed'

    def dispatch(self, job_id, model_ids):
        for index, model_id in enumerate(model_ids):
            tasks = self.cloud_queue if self.models[model_id].adapter == 'vlm' else self.local_queues[model_id]
            tasks.put((job_id, index, model_id))

    def reserve_vlm(self, job_id, index):
        # UTC day, transactionally reserved before predict; failed calls still count.
        day = datetime.now(timezone.utc).date().isoformat()
        with self.lock, closing(sqlite3.connect(self.data / 'vlm-usage.sqlite3')) as db, db:
            db.execute('BEGIN IMMEDIATE')
            used = db.execute('SELECT count(*) FROM attempts WHERE day=?', (day,)).fetchone()[0]
            if used >= self.daily_limit:
                raise QuotaExceeded('今日云端调用额度已用完，请次日重试或联系演示管理员')
            db.execute('INSERT INTO attempts VALUES (?, ?, ?)', (day, job_id, index))

    def update_result(self, job_id, index, **changes):
        with self.lock, self.Session.begin() as db:
            job = db.get(JobRow, job_id)
            results = list(job.results)
            results[index] = dict(results[index], **changes)
            job.results = results
            job.status = self.aggregate(results)

    def worker(self, tasks, cloud):
        adapters = {}
        try:
            while True:
                task = tasks.get()
                if task is None or self.stopping.is_set():
                    return
                job_id, index, model_id = task
                with nullcontext() if cloud else self.local_slots:
                    if self.stopping.is_set():
                        return
                    try:
                        self.update_result(job_id, index, status='running')
                        config = self.models[model_id]
                        with self.Session() as db:
                            job = db.get(JobRow, job_id)
                            image_path, confidence = self.path(job.image_id), job.confidence
                        with Image.open(image_path) as source:
                            image = source.convert('RGB')
                        load_ms = 0.0
                        if model_id not in adapters:
                            adapter = self.factory(config)
                            start = time.perf_counter()
                            try:
                                adapter.load()
                            except Exception:
                                adapter.unload()
                                raise
                            load_ms = (time.perf_counter() - start) * 1000
                            adapters[model_id] = adapter
                        adapter = adapters[model_id]
                        if cloud:
                            self.reserve_vlm(job_id, index)
                        start = time.perf_counter()
                        detections = [Detection.model_validate(d) for d in adapter.predict(image, confidence)]
                        inference_ms = (time.perf_counter() - start) * 1000
                        for d in detections:
                            if d.bbox_xyxy[2] > image.width or d.bbox_xyxy[3] > image.height:
                                raise ValueError('适配器返回了超出原图范围的检测框')
                        self.update_result(job_id, index, status='succeeded',
                            detections=[d.model_dump(mode='json') for d in detections],
                            vlm=adapter.evidence.model_dump(mode='json') if cloud else None,
                            load_ms=round(load_ms, 2), inference_ms=round(inference_ms, 2))
                    except Exception as exc:
                        logger.exception('Model inference failed: %s', model_id)
                        self.update_result(job_id, index, status='failed', error=str(exc) if isinstance(exc, QuotaExceeded)
                                           else '模型加载或推理失败，请检查模型配置及后端日志')
        finally:
            for adapter in adapters.values():
                try:
                    adapter.unload()
                except Exception:
                    logger.exception('Model unload failed')

    def scheduler_health(self):
        counts = {'local': {'queued': 0, 'running': 0}, 'vlm': {'queued': 0, 'running': 0}}
        with self.Session() as db:
            for job in db.scalars(select(JobRow).where(JobRow.status.not_in(TERMINAL))):
                for result in job.results:
                    if result['status'] in ('queued', 'running'):
                        kind = 'vlm' if result['model'].get('method') == 'vlm' else 'local'
                        counts[kind][result['status']] += 1
        for kind in counts:
            workers = [t for t in self.threads if t.name.startswith(f'{kind}-')]
            counts[kind].update(workers=len(workers), alive=sum(t.is_alive() for t in workers),
                                concurrency=self.cloud_limit if kind == 'vlm' else self.local_limit)
        alive = all(t.is_alive() for t in self.threads)
        return dict(status='ok' if alive else 'degraded', worker_alive=alive, **counts)

    def close(self):
        self.stopping.set()
        for tasks in self.local_queues.values():
            tasks.put(None)
        for _ in range(self.cloud_limit):
            self.cloud_queue.put(None)
        for thread in self.threads:
            thread.join()
        self.engine.dispose()
