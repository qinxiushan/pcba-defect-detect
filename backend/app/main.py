import asyncio
import importlib.util
import io
import json
import os
import threading
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
from .scheduler import Scheduler
from .schemas import HealthInfo
from .schemas import COLORS, Detection, InferenceRequest, ModelConfig, ModelResult, PublicModel, ImageInfo, JobInfo, HistoryPage, SubmittedJob, AnalyzeRequest, AnalyzeResponse

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {'succeeded', 'failed', 'partial'}


class Service(Scheduler):
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
        self.start_scheduler()

    def availability(self, config):
        if config.adapter == 'mock':
            return True, '模拟演示'
        if config.adapter == 'vlm':
            from .vlm import VlmSettings
            if not VlmSettings().api_key:
                return False, '未配置 QWEN_API_KEY 或 DASHSCOPE_API_KEY'
            if importlib.util.find_spec('dashscope') is None:
                return False, '未安装 qwen 可选依赖'
            return True, '云端零样本检测；原图将发送至阿里云，需实际调用验证'
        if not config.weights or not Path(config.weights).is_file():
            return False, '未配置有效权重文件'
        if importlib.util.find_spec('ultralytics') is None:
            return False, '未安装 YOLO 可选依赖'
        if getattr(self, 'torch_error', False):
            return False, 'YOLO 运行环境初始化失败，请检查后端日志'
        return True, '待首次加载验证'

    def path(self, image_id):
        return self.data / 'images' / f'{image_id}.png'

    def serialize(self, db, job):
        image = db.get(ImageRow, job.image_id)
        # Supply new optional fields for old rows, identically for detail and JSON export.
        results = []
        for result in job.results:
            model = dict(result['model'])
            model.setdefault('method', 'mock' if result['is_mock'] else 'yolo')
            results.append(ModelResult.model_validate(dict(result, model=model)).model_dump(mode='json'))
        return dict(id=job.id, created_at=job.created_at, status=job.status, confidence=job.confidence,
                    image=dict(id=image.id, filename=image.filename, width=image.width, height=image.height,
                               url=f'/api/v1/images/{image.id}'), results=results)


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

    @app.get('/api/v1/health', response_model=HealthInfo)
    def health():
        s = service()
        with s.Session() as db:
            db.execute(select(1))
        return s.scheduler_health()

    @app.get('/api/v1/models', response_model=list[PublicModel])
    def models():
        s = service()
        return [dict(id=m.id, name=m.name, version=m.version, author=m.author, description=m.description,
                     device=m.device, method=m.adapter, is_mock=m.adapter == 'mock', available=s.availability(m)[0],
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
            with s.lock, s.Session.begin() as db:
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
                                               author=config.author, device=config.device, method=config.adapter,
                                               provider_model=config.provider_model),
                                    is_mock=config.adapter == 'mock', status='queued', detections=[],
                                    load_ms=None, inference_ms=None, error=None))
            job_id = uuid4().hex
            db.add(JobRow(id=job_id, image_id=body.image_id, confidence=body.confidence,
                          created_at=datetime.now(timezone.utc).isoformat(), status='queued', results=results))
        s.dispatch(job_id, body.model_ids)
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
        prefix = 'SIMULATED | ' if result['is_mock'] else 'VLM ZERO-SHOT | ' if result['model'].get('method') == 'vlm' else ''
        label = f"{prefix}{model_id} | {result['model']['version']}"
        draw.rectangle((0, 0, image.width, 22), fill='#102c36')
        draw.text((5, 5), label, fill='white')
        output = io.BytesIO()
        image.save(output, format='PNG')
        return Response(output.getvalue(), media_type='image/png',
                        headers={'Content-Disposition': f'attachment; filename="{job_id}-{model_id}.png"'})

    @app.post('/api/v1/analyze', response_model=AnalyzeResponse, deprecated=True)
    def analyze(body: AnalyzeRequest):
        s = service()
        with s.Session() as db:
            if not db.get(ImageRow, body.image_id):
                raise HTTPException(404, '图片不存在')
        return {'enabled': False, 'message': '此接口已停用，请通过 /api/v1/inferences 选择 VLM 零样本检测模型；结果会持久化。'}

    return app


app = create_app()
