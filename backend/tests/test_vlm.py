import io
import json
import sys
import time
from importlib.machinery import ModuleSpec
from types import ModuleType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.schemas import ModelConfig
from app.vlm import VlmAdapter, PROMPT_VERSION


class Obj(dict):
    __getattr__ = dict.__getitem__


def verdict(assessment='suspected_defects'):
    return dict(assessment=assessment, summary='局部边缘存在突起，需复核', detections=[
        dict(class_name='spur', confidence=.8, bbox_xyxy=[100,200,400,600], reason='边缘向外突起'),
    ] if assessment == 'suspected_defects' else [])


@pytest.fixture
def provider(monkeypatch):
    pytest.importorskip('requests', reason='VLM transport requires the qwen extra')
    state = {'payload': verdict(), 'calls': []}
    def call(**kwargs):
        state['calls'].append(kwargs)
        if state.get('exception'):
            raise TimeoutError('secret provider detail')
        content = state.get('raw', json.dumps(state['payload'], ensure_ascii=False))
        return Obj(status_code=state.get('status', 200), request_id='request-test',
                   output=Obj(choices=[Obj(finish_reason=state.get('finish', 'stop'), message=Obj(content=[{'text':content}]))]))
    module = ModuleType('dashscope')
    module.__spec__ = ModuleSpec('dashscope', loader=None)
    module.MultiModalConversation = SimpleNamespace(call=call)
    monkeypatch.setitem(sys.modules, 'dashscope', module)
    monkeypatch.setenv('QWEN_API_KEY', 'test-only')
    return state


def adapter():
    a = VlmAdapter(ModelConfig(id='v',name='VLM',version='v1',adapter='vlm',provider_model='qwen3-vl-plus',device='cloud'))
    a.load()
    return a


def test_image_only_prompt_coordinates_and_threshold(provider):
    a = adapter()
    results = a.predict(Image.new('RGB', (500,200)), .25)
    assert results[0].bbox_xyxy == (50,40,200,120)
    assert results[0].class_id == 1 and results[0].reason == '边缘向外突起'
    message = provider['calls'][0]['messages'][0]['content']
    assert len(message) == 2 and message[0]['image'].startswith('data:image/png;base64,')
    assert '其他检测器的预测' in message[1]['text']
    assert 'image_id' not in message[1]['text']
    assert provider['calls'][0]['request_timeout'] == 60
    assert a.evidence.prompt_version == PROMPT_VERSION
    assert a.predict(Image.new('RGB', (500,200)), .9) == []
    assert a.evidence.assessment == 'suspected_defects'
    assert a.evidence.reported_count == 1 and a.evidence.retained_count == 0


def test_missing_sdk_leaves_api_running(tmp_path, monkeypatch):
    import importlib.util
    original = importlib.util.find_spec
    monkeypatch.setenv('QWEN_API_KEY', 'test-only')
    monkeypatch.setattr(importlib.util, 'find_spec', lambda name: None if name == 'dashscope' else original(name))
    config = tmp_path/'models.json'
    config.write_text(json.dumps([dict(id='v', name='VLM', version='1', adapter='vlm', provider_model='qwen3-vl-plus')]))
    with TestClient(create_app(tmp_path/'data', config)) as client:
        model = client.get('/api/v1/models').json()[0]
        assert model['available'] is False and 'qwen' in model['availability_message']
        assert client.get('/api/v1/health').status_code == 200


@pytest.mark.parametrize('assessment', ['uncertain', 'no_visible_defects'])
def test_distinct_empty_verdicts(provider, assessment):
    provider['payload'] = verdict(assessment)
    a = adapter()
    assert a.predict(Image.new('RGB',(50,50)), .25) == []
    assert a.evidence.assessment == assessment


@pytest.mark.parametrize('case', ['json', 'bounds', 'reverse', 'nan', 'unknown', 'contradiction', 'missing', 'truncated', 'http', 'timeout'])
def test_invalid_responses_fail_instead_of_claiming_no_defects(provider, case):
    if case == 'json': provider['raw'] = 'not json'
    if case == 'bounds': provider['payload']['detections'][0]['bbox_xyxy'][2] = 1001
    if case == 'reverse': provider['payload']['detections'][0]['bbox_xyxy'][2] = 10
    if case == 'nan': provider['payload']['detections'][0]['confidence'] = float('nan')
    if case == 'unknown': provider['payload']['detections'][0]['class_name'] = 'unknown'
    if case == 'contradiction': provider['payload']['assessment'] = 'no_visible_defects'
    if case == 'missing': del provider['payload']['detections']
    if case == 'truncated': provider['finish'] = 'length'
    if case == 'http': provider['status'] = 503
    if case == 'timeout': provider['exception'] = True
    a = adapter()
    with pytest.raises((ValueError, RuntimeError)):
        a.predict(Image.new('RGB',(50,50)), .25)
    assert a.evidence is None


def wait(client, job_id):
    for _ in range(300):
        job = client.get(f'/api/v1/inferences/{job_id}').json()
        if job['status'] in {'succeeded','failed','partial'}:
            return job
        time.sleep(.01)
    pytest.fail('Task did not finish')


def test_api_persists_vlm_reopens_exports_and_deletes(tmp_path, provider):
    config = tmp_path/'models.json'
    config.write_text(json.dumps([dict(id='v',name='VLM',version='v1',adapter='vlm',provider_model='qwen3-vl-plus',device='cloud')]))
    data = tmp_path/'data'
    with TestClient(create_app(data, config)) as client:
        assert client.get('/api/v1/models').json()[0]['available']
        out = io.BytesIO()
        exif = Image.Exif(); exif[274] = 6
        Image.new('RGB',(200,500)).save(out,format='JPEG',exif=exif)
        img = client.post('/api/v1/images',files={'file':('secret-class-name.jpg',out.getvalue(),'image/jpeg')}).json()
        assert (img['width'],img['height']) == (500,200)
        r = client.post('/api/v1/inferences',json={'image_id':img['id'],'model_ids':['v'],'confidence':.25})
        assert r.status_code == 202
        job_id = r.json()['id']
        job = wait(client, job_id)
        assert job['status'] == 'succeeded'
        result = job['results'][0]
        assert result['is_mock'] is False
        assert result['model']['method'] == 'vlm'
        assert result['detections'][0]['bbox_xyxy'] == [50,40,200,120]
        assert result['vlm']['request_id'] == 'request-test'
        assert 'secret-class-name' not in str(provider['calls'][0]['messages'])
        assert client.get('/openapi.json').json()['components']['schemas']['VlmEvidence']
    # Reopening the same database must not call the provider again.
    with TestClient(create_app(data, config)) as client:
        assert client.get(f'/api/v1/inferences/{job_id}').json() == job
        assert client.get('/api/v1/inferences').json()['items'][0] == job
        assert client.get(f'/api/v1/inferences/{job_id}/export').json() == job
        png = client.get(f'/api/v1/inferences/{job_id}/export?format=png&model_id=v')
        assert Image.open(io.BytesIO(png.content)).size == (500,200)
        assert len(provider['calls']) == 1
        # A failed later request must not inherit the cached adapter's prior verdict.
        provider['raw'] = 'invalid'
        bad = client.post('/api/v1/inferences',json={'image_id':img['id'],'model_ids':['v']}).json()['id']
        failed = wait(client,bad)
        assert failed['status'] == 'failed' and failed['results'][0]['vlm'] is None
        assert client.delete(f'/api/v1/inferences/{job_id}').status_code == 204
        assert client.get(img['url']).status_code == 200
        assert client.delete(f'/api/v1/inferences/{bad}').status_code == 204
        assert client.get(img['url']).status_code == 404
