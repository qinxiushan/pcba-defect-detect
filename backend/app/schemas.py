from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

CLASS_NAMES = ['mouse_bite', 'spur', 'missing_hole', 'short', 'open_circuit', 'spurious_copper']
CLASS_LABELS = ['鼠咬', '毛刺', '缺失孔', '短路', '开路', '杂铜']
COLORS = ['#e86a58', '#d49b22', '#8b6bd6', '#347ddd', '#159d8a', '#c55395']


class Detection(BaseModel):
    class_id: int = Field(ge=0, le=5)
    class_name: str
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    bbox_xyxy: tuple[float, float, float, float]

    @model_validator(mode='after')
    def validate_box(self):
        import math
        x1, y1, x2, y2 = self.bbox_xyxy
        if not all(math.isfinite(v) for v in self.bbox_xyxy) or not (0 <= x1 < x2 and 0 <= y1 < y2):
            raise ValueError('Invalid detection box')
        if self.class_name != CLASS_NAMES[self.class_id]:
            raise ValueError('Class name does not match canonical ID')
        return self


class ModelConfig(BaseModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$')
    name: str
    version: str
    author: str = '团队'
    description: str = ''
    adapter: Literal['mock', 'yolo'] = 'mock'
    device: str = 'cpu'
    weights: Optional[str] = None
    register_hook: Optional[str] = Field(default=None, alias='register')
    class_map: Optional[dict[int, int]] = None
    seed: int = 0


class InferenceRequest(BaseModel):
    image_id: str
    model_ids: list[str] = Field(min_length=1, max_length=10)
    confidence: float = Field(default=0.25, ge=0, le=1)

    @model_validator(mode='after')
    def unique_models(self):
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError('模型不可重复')
        return self


class PublicModel(BaseModel):
    id: str
    name: str
    version: str
    author: str
    description: str
    device: str
    is_mock: bool
    available: bool
    availability_message: str


class ImageInfo(BaseModel):
    id: str
    width: int
    height: int
    url: str
    filename: Optional[str] = None


class ModelSnapshot(BaseModel):
    id: str
    name: str
    version: str
    author: str
    device: str


Status = Literal['queued', 'running', 'succeeded', 'failed', 'partial']


class ModelResult(BaseModel):
    model: ModelSnapshot
    is_mock: bool
    status: Status
    detections: list[Detection]
    load_ms: Optional[float]
    inference_ms: Optional[float]
    error: Optional[str]


class JobInfo(BaseModel):
    id: str
    created_at: str
    status: Status
    confidence: float
    image: ImageInfo
    results: list[ModelResult]


class HistoryPage(BaseModel):
    items: list[JobInfo]
    total: int


class SubmittedJob(BaseModel):
    id: str
    status: Status


class AnalyzeRequest(BaseModel):
    image_id: str
    detections: list[Detection] = Field(default_factory=list, max_length=200)


class AnalyzeResponse(BaseModel):
    enabled: bool
    analysis: str = ''
    message: Optional[str] = None
    error: Optional[str] = None
