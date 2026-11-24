import copy
import os
from datetime import timedelta
from unittest.mock import patch
import test_api
from test_api import WRITE, READ
from app.main import create_app
from fastapi.testclient import TestClient


class AlertTest(test_api.ApiTest):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'CHARGESENSE_VOLTAGE_LEVELS': '8,10,11',
            'CHARGESENSE_CURRENT_HYSTERESIS': '0.1',
            'CHARGESENSE_VOLTAGE_HYSTERESIS': '0.2',
            'CHARGESENSE_ALERT_HOLD_SECONDS': '0',
        })
        self.env.start()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.env.stop()

    def send(self, current, voltage=7):
        self.payload['sequence'] += 1
        self.payload['measurements'].update(currentA=current, voltageV=voltage)
        self.payload['measuredAt'] = self.clock.isoformat()
        self.assertEqual(self.post().status_code, 201)

    def test_transitions_and_hysteresis(self):
        for value in (1.2, 1.2, 0.95, 0.85, 1.2):
            self.send(value)
        events = self.get('events').json()['items']
        self.assertEqual([e['level'] for e in events], ['attention', 'normal', 'attention'])
        self.assertEqual(events[1]['kind'], 'current_recovered')

    def test_simultaneous_and_source_isolation(self):
        self.send(3.1, 11.5)
        self.send(3.1, 11.5)
        self.assertEqual(len(self.get('events').json()['items']), 2)
        self.payload['source'] = 'simulated'
        self.send(3.1, 11.5)
        self.assertEqual(len(self.get('events?source=simulated').json()['items']), 2)

    def test_state_survives_restart(self):
        self.send(1.2)
        with TestClient(create_app(self.path, WRITE, READ, levels=(1, 2, 3))) as client:
            self.payload['sequence'] += 1
            self.assertEqual(client.post('/api/v1/telemetry', json=self.payload, headers=self.write).status_code, 201)
        self.assertEqual(len(self.get('events').json()['items']), 1)

    def test_old_sequence_cannot_recover(self):
        self.payload['sequence'] = 10
        self.send(3.1)
        self.payload['sequence'] = 0
        self.send(0.5)
        self.assertEqual(len(self.get('events').json()['items']), 1)

    def test_hold_and_invalid_interrupt(self):
        self.app.state.alert_rules.hold = 4
        self.send(1.2)
        self.clock += timedelta(seconds=2)
        self.send(1.2)
        self.assertEqual(self.get('events').json()['items'], [])
        self.clock += timedelta(seconds=2)
        self.send(1.2)
        self.assertEqual(len(self.get('events').json()['items']), 1)
        self.clock += timedelta(seconds=1)
        self.send(2.2)
        self.payload['sequence'] += 1
        self.payload['quality'] = 'invalid'
        self.payload['measurements'] = {}
        self.assertEqual(self.post().status_code, 201)
        self.payload['quality'] = 'valid'
        self.clock += timedelta(seconds=5)
        self.send(2.2)
        self.assertEqual([e['level'] for e in self.get('events').json()['items']], ['diagnostic', 'attention'])

    def test_configuration_validation(self):
        for name, value in [('CHARGESENSE_VOLTAGE_LEVELS', '10,8,11'),
                            ('CHARGESENSE_VOLTAGE_HYSTERESIS', 'nan'),
                            ('CHARGESENSE_ALERT_HOLD_SECONDS', '-1')]:
            with self.subTest(name=name), patch.dict(os.environ, {name: value}):
                with self.assertRaises(RuntimeError):
                    with TestClient(create_app(self.path, WRITE, READ)):
                        pass

    def test_event_details_and_stale_packet(self):
        self.send(0.5, 11.5)
        event = self.get('events').json()['items'][0]
        self.assertEqual((event['kind'], event['value'], event['threshold'], event['unit']),
                         ('voltage_threshold', 11.5, 11.0, 'V'))
        self.payload['sequence'] += 1
        self.payload['measurements']['voltageV'] = 1
        self.payload['measuredAt'] = (self.clock - timedelta(seconds=20)).isoformat()
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(len(self.get('events').json()['items']), 1)

    def test_gap_restarts_confirmation(self):
        self.app.state.alert_rules.hold = 4
        self.send(1.2)
        self.clock += timedelta(seconds=16)
        self.send(1.2)
        self.assertEqual(self.get('events').json()['items'], [])
        self.clock += timedelta(seconds=4)
        self.send(1.2)
        self.assertEqual(len(self.get('events').json()['items']), 1)


    def test_all_transitions_are_events(self):
        # Both metrics: normal -> critical -> alert -> attention -> alert -> normal.
        for current, voltage in [(0.5, 7), (3.5, 12), (2.5, 10.5),
                                 (1.5, 8.5), (2.5, 10.5), (0.5, 7)]:
            self.send(current, voltage)
        events = self.get('events').json()['items']
        for metric in ('current', 'voltage'):
            self.assertEqual([e['level'] for e in reversed(events)
                              if e['kind'].startswith(metric)],
                             ['critical', 'alert', 'attention', 'alert', 'normal'])

    def test_downgrade_persists_across_restart(self):
        self.send(3.5)
        self.send(1.5)
        self.assertEqual(len(self.get('events').json()['items']), 2)
        with TestClient(create_app(self.path, WRITE, READ, levels=(1, 2, 3),
                                  now=lambda: self.clock)) as client:
            self.payload['sequence'] += 1
            self.payload['measurements']['currentA'] = 2.5
            self.assertEqual(client.post('/api/v1/telemetry', json=self.payload,
                                         headers=self.write).status_code, 201)
        self.assertEqual([e['level'] for e in self.get('events').json()['items']],
                         ['alert', 'attention', 'critical'])
