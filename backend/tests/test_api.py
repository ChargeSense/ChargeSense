import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from app.main import create_app

WRITE = 'test-device-key-000000000000000000'
READ = 'test-read-key-00000000000000000000'


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'test.db'
        self.clock = datetime(2026, 11, 16, 15, tzinfo=timezone.utc)
        self.app = create_app(self.path, WRITE, READ, levels=(1, 2, 3), now=lambda: self.clock)
        self.client = TestClient(self.app).__enter__()
        self.write = {'X-API-Key': WRITE}
        self.read = {'X-API-Key': READ}
        self.payload = {'schemaVersion': 1, 'stationId': 'bancada-01',
                        'bootId': '8505ad41-ed6c-43e2-b190-f079e292bca8',
                        'sequence': 0, 'source': 'sensor', 'measuredAt': self.clock.isoformat(),
                        'uptimeMs': 1000, 'quality': 'valid',
                        'measurements': {'currentA': 0.5, 'voltageV': None, 'activePowerW': None, 'panelTempC': None}}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def post(self, payload=None):
        return self.client.post('/api/v1/telemetry', json=payload or self.payload, headers=self.write)

    def get(self, path, **kwargs):
        return self.client.get('/api/v1/stations/bancada-01/' + path, headers=self.read, **kwargs)

    def test_health_docs_and_auth(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.get('/openapi.json').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/stations/bancada-01/latest').status_code, 401)
        self.assertEqual(self.client.post('/api/v1/telemetry', json=self.payload, headers=self.read).status_code, 401)
        self.assertEqual(self.client.get('/api/v1/stations/bancada-01/latest', headers=self.write).status_code, 401)

    def test_create_duplicate_conflict(self):
        a, b = self.post(), self.post()
        self.assertEqual((a.status_code, b.status_code), (201, 200))
        self.assertEqual(a.json()['id'], b.json()['id'])
        self.assertTrue(b.json()['duplicate'])
        self.payload['measurements']['currentA'] = 0.7
        self.assertEqual(self.post().status_code, 409)

    def test_simulation_is_separate(self):
        self.payload['source'] = 'simulated'
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.get('latest').status_code, 404)
        self.assertEqual(self.get('latest?source=simulated').status_code, 200)
        self.assertEqual(self.get('status').json()['connection'], 'never_seen')

    def test_stale_and_duplicate_does_not_refresh_connection(self):
        self.post()
        self.clock += timedelta(seconds=16)
        self.post()
        status = self.get('status').json()
        self.assertEqual(status['connection'], 'offline')
        self.assertEqual(status['freshness'], 'stale')

    def test_delayed_packet_not_fresh(self):
        self.payload['measuredAt'] = (self.clock-timedelta(hours=1)).isoformat()
        self.post()
        status = self.get('status').json()
        self.assertEqual(status['connection'], 'online')
        self.assertEqual(status['freshness'], 'stale')

    def test_unclocked_reading(self):
        self.payload['measuredAt'] = None
        self.post()
        self.assertEqual(self.get('status').json()['freshness'], 'unknown')

    def test_out_of_order_does_not_replace_latest(self):
        self.payload['sequence'] = 2
        self.payload['measuredAt'] = None
        self.post()
        self.clock += timedelta(seconds=1)
        self.payload['sequence'] = 1
        self.post()
        self.assertEqual(self.get('latest').json()['sequence'], 2)

    def test_nulls_and_diagnostic_events(self):
        self.payload['quality'] = 'uncalibrated'
        self.assertEqual(self.post().status_code, 422)
        self.payload['measurements']['currentA'] = None
        self.assertEqual(self.post().status_code, 201)
        self.post()
        events = self.get('events').json()['items']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['kind'], 'measurement_uncalibrated')

    def test_three_threshold_levels(self):
        for seq, current in enumerate((1, 2, 3)):
            self.payload['sequence'] = seq
            self.payload['measurements']['currentA'] = current
            self.assertEqual(self.post().status_code, 201)
        self.assertEqual([x['level'] for x in self.get('events').json()['items']], ['critical', 'alert', 'attention'])

    def test_validation(self):
        variants = []
        for field, value in [('sequence', -1), ('sequence', True), ('stationId', '../other'),
                             ('bootId', 'bad'), ('schemaVersion', 2), ('source', 'manual'),
                             ('measuredAt', '2026-11-16T15:00:00'),
                             ('measuredAt', (self.clock+timedelta(minutes=1)).isoformat())]:
            p = copy.deepcopy(self.payload); p[field] = value; variants.append(p)
        p = copy.deepcopy(self.payload); p['measurements']['currentA'] = -1; variants.append(p)
        p = copy.deepcopy(self.payload); p['measurements']['activePowerW'] = 2; variants.append(p)
        p = copy.deepcopy(self.payload); p['unexpected'] = 2; variants.append(p)
        for p in variants:
            with self.subTest(payload=p):
                self.assertEqual(self.post(p).status_code, 422)
        p = copy.deepcopy(self.payload); p['stationId'] = 'another-station'
        self.assertEqual(self.post(p).status_code, 404)

    def test_nan_infinity_and_size(self):
        for value in ['NaN', 'Infinity', '1e999']:
            raw = json.dumps(self.payload).replace('0.5', value)
            self.assertEqual(self.client.post('/api/v1/telemetry', content=raw,
                headers={**self.write, 'Content-Type': 'application/json'}).status_code, 422)
        self.assertEqual(self.client.post('/api/v1/telemetry', content=' '*8193, headers=self.write).status_code, 413)

    def test_pagination(self):
        for seq in range(3):
            self.payload['sequence'] = seq
            self.post()
        first = self.get('readings?limit=2').json()
        second = self.get('readings?limit=2&before_id='+str(first['nextBeforeId'])).json()
        self.assertEqual(len(first['items']), 2)
        self.assertEqual(len(second['items']), 1)
        self.assertEqual(self.get('readings?limit=501').status_code, 422)

    def test_persistence(self):
        self.post()
        with TestClient(create_app(self.path, WRITE, READ)) as other:
            response = other.get('/api/v1/stations/bancada-01/latest', headers=self.read)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['measurements']['currentA'], 0.5)

    def test_concurrent_duplicates(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            codes = list(pool.map(lambda _: self.post().status_code, range(8)))
        self.assertEqual(codes.count(201), 1)
        self.assertEqual(codes.count(200), 7)

    def test_unsafe_configuration_rejected(self):
        with self.assertRaises(RuntimeError):
            with TestClient(create_app(self.path, WRITE, WRITE)):
                pass


if __name__ == '__main__':
    unittest.main()
