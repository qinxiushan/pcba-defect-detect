import asyncio
import importlib.util
import io
import json
import logging
import os
import queue
import threading
import time
import warnings
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from sqlalchemy import select, func

from .adapters import create_adapter
from .db import ImageRow, JobRow, init_db
from .schemas import COLORS, Detection, InferenceRequest, ModelConfig, PublicModel, ImageInfo, JobInfo, HistoryPage, SubmittedJob

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'succeeded', 'failed', 'partial'}
logger = logging.getLogger(__name__)


class Service:
    def __init__(self, data_dir, config_path, factory):
        self.data = Path(data_dir)
        (self.data / 'images').mkdir(parents=True, exist_ok=True)
        self.engine, self.Session = init_db(self.data / 'history.sqlite3')
        configs = [ModelConfig.model_validate(m) for m in json.loads(Path(config_path).read_text(encoding='utf-8'))]
        self.models = {m.id: m for m in configs}
        if len(self.models) != len(configs):
            raise ValueError('模型 ID 重复')
        for config in configs:
            if config.weights:
                config.weights = str((Path(config_path).parent / config.weights).resolve())
        self.factory = factory
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        self.current = None
        self.adapter = None
        self.stopping = threading.Event()
        with self.Session.begin() as db:
            for job in db.scalars(select(JobRow).where(JobRow.status.not_in(TERMINAL))):
                job.status = 'failed'
                job.results = [dict(r, status='failed', error='服务重启中断，请重新提交')
                               if r['status'] not in TERMINAL else r for r in job.results]
        self.thread = threading.Thread(target=self.worker, name='inference-worker', daemon=True)
        self.thread.start()

    def availability(self, config):
        if config.adapter == 'mock':
            return True, '模拟演示'
        if not config.weights or not Path(config.weights).is_file():
            return False, '未配置有效权重文件'
        if importlib.util.find_spec('ultralytics') is None:
            return False, '未安装 YOLO 可选依赖'
        return True, '待首次加载验证'

    def path(self, image_id):
        return self.data / 'images' / f'{image_id}.png'

    def close(self):
        self.stopping.set()
        self.queue.put(None)
        self.thread.join()
        self.engine.dispose()

    def update_result(self, job_id, index, **changes):
        with self.Session.begin() as db:
            job = db.get(JobRow, job_id)
            results = list(job.results)
            results[index] = dict(results[index], **changes)
            job.results = results
            job.status = 'running'

    def worker(self):
        try:
            while not self.stopping.is_set():
                job_id = self.queue.get()
                if job_id is None:
                    return
                try:
                    self.run_job(job_id)
                except Exception:
                    logger.exception('Unexpected task failure: %s', job_id)
                    with self.Session.begin() as db:
                        job = db.get(JobRow, job_id)
                        job.status = 'failed'
                        job.results = [dict(r, status='failed', error='任务执行异常，请检查后端日志')
                                       if r['status'] not in TERMINAL else r for r in job.results]
        finally:
            if self.adapter:
                self.adapter.unload()

    def run_job(self, job_id):
        with self.Session() as db:
            job = db.get(JobRow, job_id)
            image_path = self.path(job.image_id)
            results = job.results
            confidence = job.confidence
        with Image.open(image_path) as source:
            image = source.convert('RGB')
        for index, result in enumerate(results):
            if self.stopping.is_set():
                return
            config = self.models[result['model']['id']]
            self.update_result(job_id, index, status='running')
            try:
                load_ms = 0.0
                if self.current != config.id:
                    if self.adapter:
                        self.adapter.unload()
                    self.adapter = None
                    self.current = None
                    adapter = self.factory(config)
                    start = time.perf_counter()
                    try:
                        adapter.load()
                    except Exception:
                        adapter.unload()
                        raise
                    load_ms = (time.perf_counter() - start) * 1000
                    self.adapter, self.current = adapter, config.id
                start = time.perf_counter()
                detections = [Detection.model_validate(d) for d in self.adapter.predict(image.copy(), confidence)]
                inference_ms = (time.perf_counter() - start) * 1000
                for d in detections:
                    if d.bbox_xyxy[2] > image.width or d.bbox_xyxy[3] > image.height:
                        raise ValueError('适配器返回了超出原图范围的检测框')
                self.update_result(job_id, index, status='succeeded',
                                   detections=[d.model_dump(mode='json') for d in detections],
                                   load_ms=round(load_ms, 2), inference_ms=round(inference_ms, 2))
            except Exception:
                logger.exception('Model inference failed: %s', config.id)
                self.update_result(job_id, index, status='failed', error='模型加载或推理失败，请检查模型配置及后端日志')
        with self.Session.begin() as db:
            job = db.get(JobRow, job_id)
            successes = sum(r['status'] == 'succeeded' for r in job.results)
            job.status = 'succeeded' if successes == len(job.results) else 'partial' if successes else 'failed'

    def serialize(self, db, job):
        image = db.get(ImageRow, job.image_id)
        return dict(id=job.id, created_at=job.created_at, status=job.status, confidence=job.confidence,
                    image=dict(id=image.id, filename=image.filename, width=image.width, height=image.height,
                               url=f'/api/v1/images/{image.id}'), results=job.results)


def create_app(data_dir=None, config_path=None, adapter_factory=create_adapter):
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = Service(data_dir or os.getenv('PCB_DATA_DIR', ROOT / 'data'),
                                    config_path or os.getenv('PCB_MODELS_CONFIG', ROOT / 'models.json'), adapter_factory)
        yield
        await asyncio.to_thread(app.state.service.close)

    app = FastAPI(title='PCB 缺陷检测 API', version='1.0.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware,
                       allow_origins=os.getenv('PCB_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','),
                       allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Content-Type'])

    def service():
        return app.state.service

    @app.get('/api/v1/health')
    def health():
        s = service()
        with s.Session() as db:
            db.execute(select(1))
        return {'status': 'ok', 'worker_alive': s.thread.is_alive()}

    @app.get('/api/v1/models', response_model=list[PublicModel])
    def models():
        s = service()
        return [dict(id=m.id, name=m.name, version=m.version, author=m.author, description=m.description,
                     device=m.device, is_mock=m.adapter == 'mock', available=s.availability(m)[0],
                     availability_message=s.availability(m)[1]) for m in s.models.values()]

    @app.post('/api/v1/images', status_code=201, response_model=ImageInfo)
    def upload(file: UploadFile):
        raw = file.file.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(413, '图片不能超过 10 MB')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as source:
                    if source.format not in {'JPEG', 'PNG'}:
                        raise HTTPException(415, '仅支持 JPEG 和 PNG 图片')
                    if source.width * source.height > 25_000_000:
                        raise HTTPException(413, '图片不能超过 2500 万像素')
                    image = ImageOps.exif_transpose(source).convert('RGB')
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(422, '图片损坏或无法解码')
        s = service()
        image_id = uuid4().hex
        image.save(s.path(image_id))
        try:
            with s.Session.begin() as db:
                db.add(ImageRow(id=image_id, filename=Path(file.filename or 'image').name,
                                width=image.width, height=image.height))
        except Exception:
            s.path(image_id).unlink(missing_ok=True)
            raise
        return dict(id=image_id, width=image.width, height=image.height, url=f'/api/v1/images/{image_id}')

    @app.get('/api/v1/images/{image_id}')
    def get_image(image_id: str):
        s = service()
        with s.Session() as db:
            if not db.get(ImageRow, image_id):
                raise HTTPException(404, '图片不存在')
        return FileResponse(s.path(image_id), media_type='image/png')

    @app.post('/api/v1/inferences', status_code=202, response_model=SubmittedJob)
    def submit(body: InferenceRequest):
        s = service()
        with s.lock, s.Session.begin() as db:
            if not db.get(ImageRow, body.image_id):
                raise HTTPException(404, '图片不存在')
            pending = db.scalar(select(func.count()).select_from(JobRow).where(JobRow.status.not_in(TERMINAL)))
            if pending >= 20:
                raise HTTPException(429, '任务队列已满，请稍后重试')
            results = []
            for model_id in body.model_ids:
                config = s.models.get(model_id)
                if config is None:
                    raise HTTPException(404, f'未知模型：{model_id}')
                available, reason = s.availability(config)
                if not available:
                    raise HTTPException(409, f'{config.name}：{reason}')
                results.append(dict(model=dict(id=config.id, name=config.name, version=config.version,
                                               author=config.author, device=config.device),
                                    is_mock=config.adapter == 'mock', status='queued', detections=[],
                                    load_ms=None, inference_ms=None, error=None))
            job_id = uuid4().hex
            db.add(JobRow(id=job_id, image_id=body.image_id, confidence=body.confidence,
                          created_at=datetime.now(timezone.utc).isoformat(), status='queued', results=results))
        s.queue.put(job_id)
        return {'id': job_id, 'status': 'queued'}

    @app.get('/api/v1/inferences', response_model=HistoryPage)
    def history(page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
        s = service()
        with s.Session() as db:
            jobs = db.scalars(select(JobRow).order_by(JobRow.created_at.desc()).offset((page-1)*page_size).limit(page_size))
            return {'items': [s.serialize(db, j) for j in jobs],
                    'total': db.scalar(select(func.count()).select_from(JobRow))}

    @app.get('/api/v1/inferences/{job_id}', response_model=JobInfo)
    def detail(job_id: str):
        s = service()
        with s.Session() as db:
            job = db.get(JobRow, job_id)
            if not job:
                raise HTTPException(404, '记录不存在')
            return s.serialize(db, job)

    @app.delete('/api/v1/inferences/{job_id}', status_code=204)
    def delete(job_id: str):
        s = service()
        with s.lock, s.Session.begin() as db:
            job = db.get(JobRow, job_id)
            if not job:
                raise HTTPException(404, '记录不存在')
            if job.status not in TERMINAL:
                raise HTTPException(409, '运行中的任务不能删除')
            image_id = job.image_id
            db.delete(job)
            db.flush()
            if not db.scalar(select(func.count()).select_from(JobRow).where(JobRow.image_id == image_id)):
                db.delete(db.get(ImageRow, image_id))
                s.path(image_id).unlink(missing_ok=True)
        return Response(status_code=204)

    @app.get('/api/v1/inferences/{job_id}/export')
    def export(job_id: str, format: str = Query('json', pattern='^(json|png)$'), model_id: str | None = None):
        job = detail(job_id)
        if job['status'] not in TERMINAL:
            raise HTTPException(409, '任务尚未结束')
        if format == 'json':
            return Response(json.dumps(job, ensure_ascii=False, indent=2), media_type='application/json',
                            headers={'Content-Disposition': f'attachment; filename="{job_id}.json"'})
        result = next((r for r in job['results'] if r['model']['id'] == model_id), None)
        if result is None or result['status'] != 'succeeded':
            raise HTTPException(409, '请选择一个推理成功的模型')
        with Image.open(service().path(job['image']['id'])) as source:
            image = source.convert('RGB')
        draw = ImageDraw.Draw(image)
        for d in result['detections']:
            color = COLORS[d['class_id']]
            draw.rectangle(d['bbox_xyxy'], outline=color, width=max(2, image.width//300))
            draw.text((d['bbox_xyxy'][0], max(0, d['bbox_xyxy'][1]-12)),
                      f"{d['class_name']} {d['confidence']:.2f}", fill=color)
        label = f"{'SIMULATED | ' if result['is_mock'] else ''}{model_id} | {result['model']['version']}"
        draw.rectangle((0, 0, image.width, 22), fill='#102c36')
        draw.text((5, 5), label, fill='white')
        output = io.BytesIO()
        image.save(output, format='PNG')
        return Response(output.getvalue(), media_type='image/png',
                        headers={'Content-Disposition': f'attachment; filename="{job_id}-{model_id}.png"'})

    return app


app = create_app()
