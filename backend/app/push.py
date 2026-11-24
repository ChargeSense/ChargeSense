"""Durable Expo push outbox. Run one worker per backend process (leases in SQLite)."""
import asyncio
import json
import logging
import os
import time
import httpx

log = logging.getLogger('uvicorn.error')
KINDS = ('current_threshold', 'voltage_threshold', 'current_recovered', 'voltage_recovered')


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS push_devices (
            token TEXT PRIMARY KEY, station TEXT NOT NULL, source TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS push_jobs (
            id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL,
            token TEXT NOT NULL, message TEXT NOT NULL,
            phase TEXT NOT NULL DEFAULT 'send', ticket TEXT,
            attempts INTEGER NOT NULL DEFAULT 0, due REAL NOT NULL DEFAULT 0,
            expires REAL NOT NULL, error TEXT,
            UNIQUE(event_id, token)
        );
        CREATE INDEX IF NOT EXISTS push_due ON push_jobs(phase, due);
    ''')

    columns = {row[1] for row in db.execute('PRAGMA table_info(event_details)')}
    if 'push_eligible' not in columns:
        db.execute('ALTER TABLE event_details ADD COLUMN push_eligible INTEGER NOT NULL DEFAULT 1')


def enqueue(db, reading_id):
    for event in db.execute('SELECT * FROM events WHERE reading_id=?', (reading_id,)).fetchall():
        if event['kind'] not in KINDS:
            continue
        metric = 'Tensão' if event['kind'].startswith('voltage') else 'Corrente'
        level = {'attention': 'Atenção', 'alert': 'Alerta', 'critical': 'Crítico', 'normal': 'Normalizado'}[event['level']]
        details = db.execute('SELECT * FROM event_details WHERE event_id=?', (event['id'],)).fetchone()
        if not details['push_eligible']:
            continue
        body = f"{metric}: {details['value']:.3f} {details['unit']}. Estação {event['station']} ({event['source']})."
        for device in db.execute('SELECT token FROM push_devices WHERE station=? AND source=?',
                                 (event['station'], event['source'])).fetchall():
            message = dict(to=device['token'], title=f'ChargeSense · {level}', body=body,
                           sound='default', priority='high', channelId='chargesense-alerts', ttl=900,
                           data=dict(eventId=event['id'], stationId=event['station'], source=event['source'], level=event['level']))
            db.execute('INSERT OR IGNORE INTO push_jobs(event_id,token,message,expires) VALUES(?,?,?,?)',
                       (event['id'], device['token'], json.dumps(message), time.time()+900))


class PushWorker:
    def __init__(self, store):
        self.store = store

    def claim(self):
        now = time.time()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE push_jobs SET phase='failed',error='expired' WHERE phase='send' AND expires<?", (now,))
            row = db.execute("SELECT * FROM push_jobs WHERE phase IN ('send','receipt') AND due<=? ORDER BY id LIMIT 1", (now,)).fetchone()
            if row:
                db.execute('UPDATE push_jobs SET due=? WHERE id=?', (now+60, row['id']))
                return dict(row)

    def finish(self, job, phase, error=None, ticket=None, delay=0):
        with self.store.connect() as db:
            db.execute('UPDATE push_jobs SET phase=?,error=?,ticket=COALESCE(?,ticket),due=?,attempts=attempts+1 WHERE id=?',
                       (phase, error, ticket, time.time()+delay, job['id']))
            if error == 'DeviceNotRegistered':
                db.execute('DELETE FROM push_devices WHERE token=?', (job['token'],))
                db.execute("UPDATE push_jobs SET phase='failed',error=? WHERE token=? AND phase IN ('send','receipt')", (error, job['token']))
        if error:
            log.warning('Push job %s: %s', job['id'], error)

    async def step(self, client):
        job = self.claim()
        if not job:
            return False
        try:
            headers = {}
            access = os.getenv('CHARGESENSE_EXPO_ACCESS_TOKEN')
            if access:
                headers['Authorization'] = 'Bearer ' + access
            receipt = job['phase'] == 'receipt'
            body = {'ids': [job['ticket']]} if receipt else json.loads(job['message'])
            if not receipt:
                body['ttl'] = max(1, int(job['expires'] - time.time()))
            response = await client.post('https://exp.host/--/api/v2/push/' + ('getReceipts' if receipt else 'send'),
                                         json=body, headers=headers)
            response.raise_for_status()
            data = response.json()['data']
            result = data.get(job['ticket']) if receipt else (data[0] if isinstance(data, list) else data)
            if receipt and result is None:
                self.finish(job, 'receipt' if job['attempts'] < 30 else 'failed',
                            error=None if job['attempts'] < 30 else 'ReceiptUnavailable', delay=900)
            elif result.get('status') == 'ok':
                if receipt:
                    self.finish(job, 'done')
                else:
                    self.finish(job, 'receipt', ticket=result['id'], delay=900)
            else:
                code = result.get('details', {}).get('error', 'ExpoRejected')
                self.finish(job, 'send' if code == 'MessageRateExceeded' and job['attempts'] < 8 else 'failed',
                            error=code, delay=min(300, 2 ** (job['attempts']+1)))
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
            permanent = isinstance(error, httpx.HTTPStatusError) and 400 <= error.response.status_code < 500 and error.response.status_code != 429
            self.finish(job, 'failed' if permanent or job['attempts'] >= 8 else job['phase'],
                        error=f'HTTP{error.response.status_code}' if isinstance(error, httpx.HTTPStatusError) else type(error).__name__, delay=min(300, 2 ** (job['attempts']+1)))
        return True

    async def run(self):
        async with httpx.AsyncClient(timeout=15) as client:
            while True:
                try:
                    worked = await self.step(client)
                except Exception:
                    log.exception('Falha no worker push')
                    worked = False
                await asyncio.sleep(0.1 if worked else 2)
