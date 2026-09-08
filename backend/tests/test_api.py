import io
import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.adapters import MockAdapter, YoloAdapter
from app.db import JobRow
from app.main import create_app
from app.schemas import CLASS_NAMES, Detection, ModelConfig


@pytest.fixture
def config(tmp_path):
    path = tmp_path / 'models.json'
    path.write_text(json.dumps([
        dict(id='a', name='A', version='1', adapter='mock', seed=1),
        dict(id='b', name='B', version='2', adapter='mock', seed=2),
    ]))
    return path


def picture(size=(120, 80), format='PNG', **kwargs):
    output = io.BytesIO()
    Image.new('RGB', size, '#59735c').save(output, format=format, **kwargs)
    return output.getvalue()


def upload(client, raw=None):
    response = client.post('/api/v1/images', files={'file': ('board.png', raw or picture(), 'image/png')})
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, image_id, ids=None, confidence=.25):
    response = client.post('/api/v1/inferences', json=dict(image_id=image_id, model_ids=ids or ['a','b'], confidence=confidence))
    assert response.status_code == 202, response.text
    return response.json()['id']


def wait_job(client, job_id):
    for _ in range(200):
        job = client.get(f'/api/v1/inferences/{job_id}').json()
        if job['status'] in {'succeeded','failed','partial'}:
            return job
        time.sleep(.01)
    pytest.fail('Task did not finish')


def test_full_flow_persistence_exports_and_cleanup(tmp_path, config):
    data = tmp_path/'data'
    with TestClient(create_app(data,config)) as client:
        assert client.get('/api/v1/health').json()['worker_alive']
        assert len(client.get('/api/v1/models').json()) == 2
        image = upload(client)
        job_id = submit(client,image['id'])
        job = wait_job(client,job_id)
        assert job['status']=='succeeded'
        assert all(r['is_mock'] and r['detections'] for r in job['results'])
        for r in job['results']:
            for d in r['detections']:
                assert d['class_name']==CLASS_NAMES[d['class_id']]
                x1,y1,x2,y2=d['bbox_xyxy']
                assert 0<=x1<x2<=120 and 0<=y1<y2<=80
        exported=client.get(f'/api/v1/inferences/{job_id}/export').json()
        assert exported==job
        png=client.get(f'/api/v1/inferences/{job_id}/export?format=png&model_id=a')
        assert Image.open(io.BytesIO(png.content)).size==(120,80)
        assert png.content!=client.get(image['url']).content
        second=submit(client,image['id'],confidence=1)
        assert all(not r['detections'] for r in wait_job(client,second)['results'])
        assert client.delete(f'/api/v1/inferences/{second}').status_code==204
        assert client.get(image['url']).status_code==200
    configs=json.loads(config.read_text());configs[0]['version']='changed';config.write_text(json.dumps(configs))
    with TestClient(create_app(data,config)) as client:
        assert client.get(f'/api/v1/inferences/{job_id}').json()['results'][0]['model']['version']=='1'
        assert client.get('/api/v1/inferences').json()['total']==1
        assert client.delete(f'/api/v1/inferences/{job_id}').status_code==204
        assert client.get(image['url']).status_code==404
        assert not (data/'images'/f"{image['id']}.png").exists()


def test_invalid_inputs_and_orientation(tmp_path, config):
    with TestClient(create_app(tmp_path/'data',config)) as client:
        assert client.post('/api/v1/images',files={'file':('bad.png',b'bad')}).status_code==422
        assert client.post('/api/v1/images',files={'file':('fake.png',picture(format='GIF'))}).status_code==415
        assert client.post('/api/v1/images',files={'file':('big.png',b'x'*(10*1024*1024+1))}).status_code==413
        assert client.post('/api/v1/images',files={'file':('large.png',picture((5001,5000)))}).status_code==413
        exif=Image.Exif();exif[274]=6
        image=upload(client,picture(format='JPEG',exif=exif))
        assert (image['width'],image['height'])==(80,120)
        assert client.get('/api/v1/images/unknown').status_code==404
        for ids,code in [(['unknown'],404),(['a','a'],422),([],422)]:
            assert client.post('/api/v1/inferences',json=dict(image_id=image['id'],model_ids=ids)).status_code==code
        assert client.post('/api/v1/inferences',json=dict(image_id='missing',model_ids=['a'])).status_code==404
        assert client.post('/api/v1/inferences',json=dict(image_id=image['id'],model_ids=['a'],confidence=2)).status_code==422


def test_failure_isolation_and_queue_capacity(tmp_path, config):
    gate=threading.Event()
    class Controlled(MockAdapter):
        def predict(self,image,confidence):
            assert gate.wait(10)
            if self.config.id=='a':
                raise RuntimeError('intentional test failure')
            return super().predict(image,confidence)
    with TestClient(create_app(tmp_path/'data',config,Controlled)) as client:
        try:
            image=upload(client)
            ids=[submit(client,image['id']) for _ in range(20)]
            assert client.delete(f'/api/v1/inferences/{ids[0]}').status_code==409
            assert client.get(f'/api/v1/inferences/{ids[0]}/export').status_code==409
            assert client.post('/api/v1/inferences',json=dict(image_id=image['id'],model_ids=['a'])).status_code==429
        finally:
            gate.set()
        job=wait_job(client,ids[0])
        assert job['status']=='partial'
        assert [r['status'] for r in job['results']]==['failed','succeeded']
        assert client.get(f'/api/v1/inferences/{ids[0]}/export?format=png&model_id=a').status_code==409


def test_restart_marks_unfinished_jobs(tmp_path,config):
    data=tmp_path/'data'
    app=create_app(data,config)
    with TestClient(app) as client:
        job_id=submit(client,upload(client)['id'])
        wait_job(client,job_id)
        with app.state.service.Session.begin() as db:
            job=db.get(JobRow,job_id)
            job.status='running'
            job.results=[dict(r,status='running') for r in job.results]
    with TestClient(create_app(data,config)) as client:
        job=client.get(f'/api/v1/inferences/{job_id}').json()
        assert job['status']=='failed'
        assert all('重启' in r['error'] for r in job['results'])


def test_mock_deterministic_and_detection_contract():
    adapter=MockAdapter(ModelConfig(id='test',name='Test',version='1'))
    image=Image.new('RGB',(60,40))
    assert adapter.predict(image,.25)==adapter.predict(image,.25)
    with pytest.raises(ValueError):
        Detection(class_id=0,class_name='short',confidence=.5,bbox_xyxy=[1,2,3,4])
    with pytest.raises(ValueError):
        Detection(class_id=0,class_name='mouse_bite',confidence=.5,bbox_xyxy=[3,2,1,4])


def test_yolo_class_mapping_without_torch():
    class Scalar:
        def __init__(self,value): self.value=value
        def item(self): return self.value
    class Coords:
        def tolist(self): return [-1,2,150,70]
    class Box:
        cls=Scalar(9);conf=Scalar(.8);xyxy=[Coords()]
    class Output:
        boxes=[Box()];names={9:'custom_short'}
    class Model:
        def predict(self,*args,**kwargs):return [Output()]
    adapter=YoloAdapter(ModelConfig(id='y',name='YOLO',version='1',adapter='yolo',class_map={9:3}))
    adapter.model=Model()
    result=adapter.predict(Image.new('RGB',(120,80)),.25)[0]
    assert result.class_name=='short' and result.bbox_xyxy==(0,2,120,70)


def test_single_model_cache_and_invalid_adapter_output(tmp_path,config):
    events=[]
    class Tracked(MockAdapter):
        def load(self): events.append(('load',self.config.id))
        def unload(self): events.append(('unload',self.config.id))
        def predict(self,image,confidence):
            if self.config.id=='b':
                return [Detection(class_id=0,class_name='mouse_bite',confidence=.8,bbox_xyxy=(0,0,999,999))]
            return super().predict(image,confidence)
    with TestClient(create_app(tmp_path/'data',config,Tracked)) as client:
        image=upload(client)
        wait_job(client,submit(client,image['id'],['a']))
        repeat=wait_job(client,submit(client,image['id'],['a']))
        assert repeat['results'][0]['load_ms']==0
        assert events==[('load','a')]
        invalid=wait_job(client,submit(client,image['id'],['b']))
        assert invalid['status']=='failed'
        assert events[:3]==[('load','a'),('unload','a'),('load','b')]
    assert events[-1]==('unload','b')


def test_openapi_contract_and_unavailable_model(tmp_path,config):
    data=json.loads(config.read_text())
    data.append(dict(id='missing',name='Missing',version='1',adapter='yolo',weights='not-found.pt'))
    config.write_text(json.dumps(data))
    with TestClient(create_app(tmp_path/'data',config)) as client:
        assert not client.get('/api/v1/models').json()[-1]['available']
        image=upload(client)
        assert client.post('/api/v1/inferences',json=dict(image_id=image['id'],model_ids=['missing'])).status_code==409
        schemas=client.get('/openapi.json').json()['components']['schemas']
        assert 'JobInfo' in schemas and 'Detection' in schemas
        assert 'bbox_xyxy' in schemas['Detection']['properties']


def test_failed_load_cleanup_does_not_import_torch(monkeypatch):
    import builtins
    import sys
    original_import = builtins.__import__
    monkeypatch.delitem(sys.modules, 'torch', raising=False)
    def guarded_import(name, *args, **kwargs):
        if name == 'torch':
            raise AssertionError('Cleanup must not retry a failed framework import')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    adapter = YoloAdapter(ModelConfig(id='cleanup', name='Cleanup', version='1', adapter='yolo'))
    adapter.unload()
