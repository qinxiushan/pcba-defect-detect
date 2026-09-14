import json
import threading
import time

from fastapi.testclient import TestClient

from app.adapters import MockAdapter
from app.main import create_app
from test_api import submit, upload, wait_job
from test_vlm import provider  # pytest fixture: no paid requests


def catalog(tmp_path, cloud=False):
    rows = [dict(id=i, name=i, version='1', adapter='mock') for i in 'abc']
    if cloud:
        rows.append(dict(id='v', name='VLM', version='1', adapter='vlm', provider_model='test'))
    path = tmp_path / 'models.json'
    path.write_text(json.dumps(rows))
    return path


def test_models_stay_on_owner_threads_and_results_do_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv('PCB_LOCAL_CONCURRENCY', '2')
    rendezvous = threading.Barrier(2)
    events = []
    owners = {}
    class Tracked(MockAdapter):
        def load(self):
            owners[self.config.id] = threading.get_ident()
            events.append(('load', self.config.id))
        def predict(self, image, confidence):
            assert owners[self.config.id] == threading.get_ident()
            if self.config.id in 'ab':
                rendezvous.wait(timeout=5)
            return super().predict(image, confidence)
        def unload(self):
            assert owners[self.config.id] == threading.get_ident()
            events.append(('unload', self.config.id))
    with TestClient(create_app(tmp_path/'data', catalog(tmp_path), Tracked)) as client:
        image = upload(client)
        for round_index in range(2):
            job = wait_job(client, submit(client, image['id'], list('abc')))
            assert job['status'] == 'succeeded'
            assert all(r['detections'] for r in job['results'])
            if round_index:
                assert all(r['load_ms'] == 0 for r in job['results'])
            assert client.get(f"/api/v1/inferences/{job['id']}/export").json() == job
        assert sorted(events) == [('load', i) for i in 'abc']
    assert sorted(events) == [(action, i) for action in ('load', 'unload') for i in 'abc']


def test_slow_cloud_does_not_block_local_and_cloud_instances_are_isolated(tmp_path, monkeypatch, provider):
    from app.vlm import VlmAdapter
    gate = threading.Event()
    both_started = threading.Barrier(3)
    instances = []
    class SlowCloud(VlmAdapter):
        def predict(self, image, confidence):
            instances.append(id(self))
            both_started.wait(timeout=5)
            assert gate.wait(5)
            return super().predict(image, confidence)
    def factory(config):
        return SlowCloud(config) if config.adapter == 'vlm' else MockAdapter(config)
    app = create_app(tmp_path/'data', catalog(tmp_path, True), factory)
    with TestClient(app) as client:
        try:
            image = upload(client)
            first = submit(client, image['id'], ['v', 'a'])
            second = submit(client, image['id'], ['v'])
            both_started.wait(timeout=5)
            local = wait_job(client, submit(client, image['id'], ['b']))
            assert local['status'] == 'succeeded'
            health = client.get('/api/v1/health').json()
            assert health['vlm']['running'] == 2 and health['worker_alive']
            assert len(set(instances)) == 2
        finally:
            gate.set()
        assert wait_job(client, first)['status'] == 'succeeded'
        assert wait_job(client, second)['status'] == 'succeeded'


def test_same_model_requests_are_serial(tmp_path, monkeypatch):
    monkeypatch.setenv('PCB_LOCAL_CONCURRENCY', '2')
    active = threading.Lock()
    class Checked(MockAdapter):
        def predict(self, image, confidence):
            assert active.acquire(blocking=False)
            try:
                time.sleep(.02)
                return super().predict(image, confidence)
            finally:
                active.release()
    with TestClient(create_app(tmp_path/'data', catalog(tmp_path), Checked)) as client:
        image = upload(client)
        jobs = [submit(client, image['id'], ['a']) for _ in range(5)]
        assert all(wait_job(client, j)['status'] == 'succeeded' for j in jobs)


def test_failed_cloud_attempt_counts_after_deletion_and_restart(tmp_path, monkeypatch, provider):
    monkeypatch.setenv('PCB_VLM_DAILY_LIMIT', '1')
    provider['exception'] = True
    config = catalog(tmp_path, True)
    data = tmp_path/'data'
    with TestClient(create_app(data, config)) as client:
        job = wait_job(client, submit(client, upload(client)['id'], ['v']))
        assert job['status'] == 'failed'
        assert len(provider['calls']) == 1
        assert client.delete(f"/api/v1/inferences/{job['id']}").status_code == 204
    with TestClient(create_app(data, config)) as client:
        job = wait_job(client, submit(client, upload(client)['id'], ['v', 'a']))
        assert job['status'] == 'partial'
        assert '额度' in job['results'][0]['error']
        assert len(provider['calls']) == 1


def test_tls_enabled_and_sdk_connection_retry_prevented(provider, monkeypatch):
    import requests
    from app.vlm import VlmAdapter
    from app.schemas import ModelConfig
    import pytest
    a = VlmAdapter(ModelConfig(id='v', name='v', version='1', adapter='vlm', provider_model='test'))
    a.load()
    assert a.session.verify is True
    count = []
    def fail(*args, **kwargs):
        count.append(1)
        raise requests.exceptions.ConnectionError('sensitive')
    monkeypatch.setattr(requests.Session, 'send', fail)
    with pytest.raises(RuntimeError, match='automatic retry disabled'):
        a.session.get('https://example.invalid')
    assert len(count) == 1
    a.unload()
