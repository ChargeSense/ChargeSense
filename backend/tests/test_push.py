import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from app.main import create_app
from app.push import PushWorker

async def idle(self):
    await asyncio.Event().wait()

class PushTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(PushWorker, 'run', idle)
        self.patch.start()
        self.app = create_app(Path(self.tmp.name)/'db', 'w'*24, 'r'*24, levels=(1,2,3))
        self.client = TestClient(self.app).__enter__()
        self.worker = PushWorker(self.app.state.store)
        self.p = dict(schemaVersion=1,stationId='bancada-01',bootId='8505ad41-ed6c-43e2-b190-f079e292bca8',
            sequence=0,source='simulated',measuredAt=None,uptimeMs=0,quality='valid',measurements=dict(currentA=3.5))
    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.patch.stop()
        self.tmp.cleanup()
    def subscribe(self, enabled=True, key='r'*24, source='simulated'):
        return self.client.post('/api/v1/stations/bancada-01/push-subscriptions',
            headers={'X-API-Key':key},json=dict(token='ExponentPushToken[test]',source=source,enabled=enabled))
    def send(self, value=3.5):
        self.p['sequence'] += 1
        self.p['measurements']['currentA'] = value
        return self.client.post('/api/v1/telemetry',headers={'X-API-Key':'w'*24},json=self.p)
    def rows(self):
        with self.app.state.store.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM push_jobs')]
    def due(self):
        with self.app.state.store.connect() as db: db.execute('UPDATE push_jobs SET due=0')
    def step(self, data, code=200):
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(code,json=data))) as c:
                await self.worker.step(c)
        asyncio.run(run())
    def test_auth_and_no_retroactive(self):
        self.assertEqual(self.subscribe(key='w'*24).status_code,401)
        self.send(); self.subscribe()
        self.assertEqual(self.rows(),[])
        self.send(0.5)
        self.assertEqual(len(self.rows()),1)
        self.p['source']='sensor'; self.send()
        self.assertEqual(len(self.rows()),1)
    def test_duplicate_downgrade_disable(self):
        self.subscribe(); self.send()
        self.client.post('/api/v1/telemetry',headers={'X-API-Key':'w'*24},json=self.p)
        self.send(2.5); self.send(1.5); self.subscribe()
        self.assertEqual(len(self.rows()),1)
        self.send(0.5)
        self.assertEqual(len(self.rows()),2)
        self.subscribe(False)
        self.assertEqual(self.rows(),[])
    def test_receipts(self):
        self.subscribe(); self.send()
        self.step({'data':{'status':'ok','id':'t'}})
        self.assertEqual(self.rows()[0]['phase'],'receipt')
        self.due(); self.step({'data':{'t':{'status':'ok'}}})
        self.assertEqual(self.rows()[0]['phase'],'done')
    def test_retry_and_invalid_device(self):
        self.subscribe(); self.send(); self.step({},503)
        self.assertEqual(self.rows()[0]['phase'],'send')
        self.assertGreater(self.rows()[0]['due'],time.time())
        self.due(); self.step({'data':{'status':'error','details':{'error':'DeviceNotRegistered'}}})
        self.assertEqual(self.rows()[0]['phase'],'failed')
        with self.app.state.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM push_devices').fetchone()[0],0)
    def test_lease_and_expiry(self):
        self.subscribe(); self.send()
        self.assertIsNotNone(self.worker.claim())
        self.assertIsNone(PushWorker(self.app.state.store).claim())
        with self.app.state.store.connect() as db: db.execute('UPDATE push_jobs SET expires=0')
        self.assertIsNone(self.worker.claim())
        self.assertEqual(self.rows()[0]['phase'],'failed')
    def test_receipt_invalid_and_switch_source(self):
        self.subscribe(); self.send(); self.step({'data':{'status':'ok','id':'t'}})
        self.due(); self.step({'data':{'t':{'status':'error','details':{'error':'DeviceNotRegistered'}}}})
        self.assertEqual(self.rows()[0]['phase'],'failed')
        self.subscribe(); self.send(0.5)
        self.subscribe(source='sensor')
        self.assertEqual(len(self.rows()),1)


    def test_all_app_events_but_only_escalations_push(self):
        self.subscribe()
        for current in [3.5, 2.5, 1.5, 2.5, 0.5]:
            self.send(current)
        with self.app.state.store.connect() as db:
            levels = [r[0] for r in db.execute('SELECT level FROM events ORDER BY id')]
            pushed = [r[0] for r in db.execute('SELECT e.level FROM push_jobs p JOIN events e ON e.id=p.event_id ORDER BY p.id')]
        self.assertEqual(levels, ['critical','alert','attention','alert','normal'])
        self.assertEqual(pushed, ['critical','alert','normal'])

    def test_diagnostics_and_scheduled_test(self):
        body = dict(token='ExponentPushToken[test]',source='simulated')
        base = '/api/v1/stations/bancada-01/'
        headers = {'X-API-Key':'r'*24}
        self.assertEqual(self.client.post(base+'push-diagnostics',json=body).status_code,401)
        self.assertEqual(self.client.post(base+'push-test',json=body,headers=headers).status_code,409)
        self.subscribe()
        info = self.client.post(base+'push-diagnostics',json=body,headers=headers).json()
        self.assertTrue(info['registered'])
        self.assertTrue(info['workerRunning'])
        self.assertIsNone(info['lastJob'])
        response = self.client.post(base+'push-test',json=body,headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertIsNone(self.worker.claim())
        second = self.client.post(base+'push-test',json=body,headers=headers).json()
        self.assertEqual(second['jobId'],response.json()['jobId'])
        self.due(); self.step({},401)
        info = self.client.post(base+'push-diagnostics',json=body,headers=headers).json()
        self.assertEqual(info['lastJob']['error'],'HTTP401')
        self.assertNotIn('token', str(info))
