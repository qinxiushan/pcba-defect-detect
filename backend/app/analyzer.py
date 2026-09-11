"""Qwen-VL 缺陷分析器（可选加分项）。

仅依赖 dashscope SDK，与 Torch/YOLO 解耦；延迟导入，未配置 API Key 时不影响后端启动。
"""
import base64
import io
import os

from PIL import Image

from .schemas import CLASS_LABELS


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

            buffer = io.BytesIO()
            image.convert('RGB').save(buffer, format='JPEG')
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            messages = [{
                'role': 'user',
                'content': [
                    {'image': f'data:image/jpeg;base64,{image_base64}'},
                    {'text': f'这是一张PCB电路板图像。检测到的缺陷有：{self._describe(detections)}。'
                             f'请分析这些缺陷的可能产生原因，并给出对应的修复或工艺改进建议。'}
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
    def _describe(detections: list[dict]) -> str:
        """把检测结果列表转成文字描述。"""
        if not detections:
            return '未检测到明显缺陷'
        counts: dict[str, int] = {}
        for d in detections:
            name = CLASS_LABELS[d.get('class_id', 0)] if 'class_id' in d else d.get('class_name', '未知缺陷')
            counts[name] = counts.get(name, 0) + 1
        return '，'.join(f'{name} {count}处' for name, count in counts.items())
