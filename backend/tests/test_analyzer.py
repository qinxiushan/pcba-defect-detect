import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from app.analyzer import QwenAnalyzer


@pytest.mark.parametrize('mode', ['success', 'error', 'exception'])
def test_provider_response_and_failure(monkeypatch, mode):
    def call(**kwargs):
        assert kwargs['messages'][0]['content'][0]['image'].startswith('data:image/jpeg;base64,')
        if mode == 'exception':
            raise RuntimeError('test failure')
        return SimpleNamespace(status_code=200 if mode == 'success' else 503, message='unavailable',
            output=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=[{'text': 'analysis'}]))]))
    monkeypatch.setitem(sys.modules, 'dashscope', SimpleNamespace(MultiModalConversation=SimpleNamespace(call=call)))
    result = QwenAnalyzer(api_key='test-only').analyze(Image.new('RGB', (10, 10)), [])
    assert result['enabled'] is True
    if mode == 'success':
        assert result['analysis'] == 'analysis'
    else:
        assert result['error']
