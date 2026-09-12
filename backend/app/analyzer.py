"""Qwen-VL 缺陷分析器（可选加分项）。

仅依赖 dashscope SDK，与 Torch/YOLO 解耦；延迟导入，未配置 API Key 时不影响后端启动。
"""
import base64
import io
import os

from PIL import Image, ImageDraw, ImageFont

from .schemas import CLASS_LABELS, CLASS_NAMES, COLORS

# 优先中文字体，找不到就退回默认字体（此时标签改用英文，避免出现方块）
_FONT_CANDIDATES = [
    'C:/Windows/Fonts/msyh.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/System/Library/Fonts/PingFang.ttc',
]


class QwenAnalyzer:
    """调用阿里云 DashScope 的 Qwen-VL 模型，对检测结果做中文成因分析。"""

    def __init__(self, api_key: str | None = None, model: str = 'qwen-vl-max'):
        self.api_key = api_key or os.getenv('QWEN_API_KEY', '')
        self.model = model

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def analyze(self, image: Image.Image, detections: list[dict]) -> dict:
        """对一张图和它的检测结果做分析。返回 {'enabled', 'analysis'} 或含 error。"""
        if not self.enabled:
            return {'enabled': False, 'message': '未配置 QWEN_API_KEY，AI 分析不可用'}

        try:
            import dashscope
            from dashscope import MultiModalConversation

            annotated = self._annotate(image.convert('RGB'), detections)

            buffer = io.BytesIO()
            annotated.save(buffer, format='JPEG')
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            messages = [{
                'role': 'user',
                'content': [
                    {'image': f'data:image/jpeg;base64,{image_base64}'},
                    {'text': f'这是一张PCB电路板图像，图中已用彩色矩形框标出检测到的缺陷位置，'
                             f'每个框左上角标注了缺陷类别和置信度。检测结果：{self._describe(detections)}。'
                             f'请结合这些框的具体位置（例如靠近板边、焊盘密集区、走线拐角处等），'
                             f'分析缺陷的可能产生原因、修复建议和工艺预防措施。'}
                ]
            }]

            response = MultiModalConversation.call(
                model=self.model,
                messages=messages,
                api_key=self.api_key,
            )

            if response.status_code == 200:
                content = response.output.choices[0].message.content
                if isinstance(content, list):
                    text = ''.join(item.get('text', '') for item in content if isinstance(item, dict))
                else:
                    text = str(content)
                return {'enabled': True, 'analysis': text}
            return {
                'enabled': True,
                'error': f'DashScope 返回错误: {response.status_code} - {getattr(response, "message", "")}',
                'analysis': '分析服务暂时不可用',
            }
        except Exception as e:
            return {'enabled': True, 'error': str(e), 'analysis': '分析服务暂时不可用'}

    @staticmethod
    def _load_font(size: int):
        for path in _FONT_CANDIDATES:
            try:
                return ImageFont.truetype(path, size), True
            except Exception:
                continue
        return ImageFont.load_default(), False

    @staticmethod
    def _annotate(image: Image.Image, detections: list[dict]) -> Image.Image:
        """把检测框画到图上，让 VLM 能"看见"缺陷位置。"""
        draw = ImageDraw.Draw(image)
        font, has_cjk = QwenAnalyzer._load_font(max(14, image.width // 40))
        line_w = max(2, image.width // 200)

        for d in detections:
            x1, y1, x2, y2 = d['bbox_xyxy']
            class_id = int(d.get('class_id', 0))
            color = COLORS[class_id % len(COLORS)]
            if has_cjk:
                label = f'{CLASS_LABELS[class_id]} {d.get("confidence", 0):.2f}'
            else:
                label = f'{CLASS_NAMES[class_id]} {d.get("confidence", 0):.2f}'

            draw.rectangle([x1, y1, x2, y2], outline=color, width=line_w)

            left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
            tw, th = right - left, bottom - top
            ty = max(0, y1 - th - 8)
            draw.rectangle([x1, ty, x1 + tw + 10, ty + th + 8], fill=color)
            draw.text((x1 + 5, ty + 4), label, fill='#ffffff', font=font)

        return image

    @staticmethod
    def _describe(detections: list[dict]) -> str:
        """把检测结果列表转成文字描述。"""
        if not detections:
            return '未检测到明显缺陷'
        counts: dict[str, int] = {}
        for d in detections:
            name = CLASS_LABELS[d.get('class_id', 0)] if 'class_id' in d else d.get('class_name', '未知缺陷')
            counts[name] = counts.get(name, 0) + 1
        return '，'.join(f'{name} {count}处' for name, count in counts.items())
