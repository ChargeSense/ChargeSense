"""Persistent threshold transitions, isolated by station and data source."""
import json
import math
import os
from datetime import datetime

LEVELS = ('normal', 'attention', 'alert', 'critical')


class AlertRules:
    def __init__(self, current_levels):
        self.rules = {}
        for metric, env, bounds in (
            ('current', 'CHARGESENSE_CURRENT', current_levels),
            ('voltage', 'CHARGESENSE_VOLTAGE', None),
        ):
            if bounds is None:
                raw = os.getenv(env + '_LEVELS', '')
                bounds = tuple(float(x) for x in raw.split(',')) if raw else ()
            margin = float(os.getenv(env + '_HYSTERESIS', '0'))
            if not math.isfinite(margin) or margin < 0:
                raise RuntimeError(env + '_HYSTERESIS deve ser finita e nao negativa')
            if bounds:
                if (len(bounds) != 3 or not all(math.isfinite(x) and x > 0 for x in bounds)
                        or not bounds[0] < bounds[1] < bounds[2] or margin >= bounds[0]):
                    raise RuntimeError(env + '_LEVELS exige tres limites positivos crescentes e histerese menor que o primeiro')
                self.rules[metric] = (bounds, margin)
        self.hold = float(os.getenv('CHARGESENSE_ALERT_HOLD_SECONDS', '0'))
        if not math.isfinite(self.hold) or self.hold < 0:
            raise RuntimeError('CHARGESENSE_ALERT_HOLD_SECONDS deve ser finito e nao negativo')

    def evaluate(self, db, data, reading_id, received):
        station, source = data['stationId'], data['source']
        def emit(kind, level, value=None, threshold=None, unit=None):
            cursor = db.execute('INSERT INTO events(reading_id,station,source,kind,level,received) VALUES(?,?,?,?,?,?)',
                       (reading_id, station, source, kind, level, received))
            db.execute('INSERT INTO event_details(event_id,value,threshold,unit) VALUES(?,?,?,?)',
                       (cursor.lastrowid, value, threshold, unit))
        if data['quality'] != 'valid':
            emit('measurement_' + data['quality'], 'diagnostic')
        for metric, (bounds, margin) in self.rules.items():
            key = (station, source, metric)
            row = db.execute('SELECT state FROM alert_states WHERE station=? AND source=? AND metric=?', key).fetchone()
            signature = [list(bounds), margin, self.hold]
            state = json.loads(row['state']) if row else {}
            if state.get('config') != signature:
                state = {'level': 0, 'config': signature}
            value = data['measurements'].get('currentA' if metric == 'current' else 'voltageV')
            stamp = datetime.fromisoformat(received).timestamp()
            # Late measurements are retained in history but cannot change live alerts.
            measured = data.get('measuredAt')
            fresh = not measured or stamp - datetime.fromisoformat(measured.replace('Z', '+00:00')).timestamp() <= 15
            if data['quality'] != 'valid' or value is None or not fresh:
                state.pop('pending', None)
            else:
                target = sum(value >= bound for bound in bounds)
                previous = state['level']
                if target < previous:
                    target = previous
                    while target > 0 and value < bounds[target - 1] - margin:
                        target -= 1
                if target == previous:
                    state.pop('pending', None)
                else:
                    pending = state.get('pending')
                    if (not pending or pending[0] != target or state.get('boot') != data['bootId']
                            or stamp - state.get('last', stamp) > 15):
                        pending = [target, stamp]
                    state['pending'] = pending
                    if stamp - pending[1] >= self.hold:
                        emit(metric + ('_recovered' if target == 0 else '_threshold'),
                             'normal' if target == 0 else LEVELS[target], value,
                             bounds[target - 1] if target else bounds[0] - margin,
                             'A' if metric == 'current' else 'V')
                        state['level'] = target
                        state.pop('pending', None)
                state['last'] = stamp
                state['boot'] = data['bootId']
            db.execute('INSERT OR REPLACE INTO alert_states(station,source,metric,state) VALUES(?,?,?,?)',
                       (*key, json.dumps(state)))
