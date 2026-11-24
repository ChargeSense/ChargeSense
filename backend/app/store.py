import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Conflict(Exception):
    pass


class Store:
    """SQLite local; manter a interface ao migrar a persistencia para AWS."""
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS event_details (
                    event_id INTEGER PRIMARY KEY REFERENCES events(id),
                    value REAL, threshold REAL, unit TEXT
                );
                CREATE TABLE IF NOT EXISTS alert_states (
                    station TEXT, source TEXT, metric TEXT, state TEXT NOT NULL,
                    PRIMARY KEY(station, source, metric)
                );
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station TEXT NOT NULL, source TEXT NOT NULL, boot TEXT NOT NULL,
                    sequence INTEGER NOT NULL, measured TEXT, received TEXT NOT NULL,
                    canonical TEXT NOT NULL,
                    UNIQUE(station, source, boot, sequence)
                );
                CREATE INDEX IF NOT EXISTS readings_station ON readings(station, source, id);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reading_id INTEGER NOT NULL REFERENCES readings(id),
                    station TEXT NOT NULL, source TEXT NOT NULL,
                    kind TEXT NOT NULL, level TEXT NOT NULL, received TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_station ON events(station, source, id);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def decode(row):
        return {'id': row['id'], **json.loads(row['canonical']), 'receivedAt': row['received']}

    def insert(self, payload, received, rules):
        data = payload.model_dump(mode='json')
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            key = (data['stationId'], data['source'], data['bootId'], data['sequence'])
            row = db.execute('SELECT * FROM readings WHERE station=? AND source=? AND boot=? AND sequence=?', key).fetchone()
            if row:
                if row['canonical'] != canonical:
                    raise Conflict('Mesmo identificador com conteudo diferente')
                return self.decode(row), True
            measured = payload.measuredAt.isoformat(timespec='microseconds') if payload.measuredAt else None
            cursor = db.execute('INSERT INTO readings(station,source,boot,sequence,measured,received,canonical) VALUES(?,?,?,?,?,?,?)',
                                (*key, measured, received, canonical))
            row = db.execute('SELECT * FROM readings WHERE id=?', (cursor.lastrowid,)).fetchone()
            # Evaluate within the same transaction: duplicates cannot notify twice.
            newer = db.execute('SELECT 1 FROM readings WHERE station=? AND source=? AND boot=? AND sequence>?', key).fetchone()
            if not newer:
                rules.evaluate(db, data, row['id'], received)
            return self.decode(row), False

    def latest(self, station, source):
        with self.connect() as db:
            # Nao regredir para sequencia anterior da mesma sessao em retransmissoes.
            row = db.execute('''SELECT r.* FROM readings r WHERE station=? AND source=?
                AND NOT EXISTS (SELECT 1 FROM readings newer
                    WHERE newer.station=r.station AND newer.source=r.source
                    AND newer.boot=r.boot AND newer.sequence>r.sequence)
                ORDER BY COALESCE(measured,received) DESC, id DESC LIMIT 1''', (station, source)).fetchone()
            return self.decode(row) if row else None

    def history(self, station, source, limit, before):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM readings WHERE station=? AND source=? AND id<? ORDER BY id DESC LIMIT ?',
                              (station, source, before, limit)).fetchall()
            return [self.decode(r) for r in rows]

    def events(self, station, source, limit, before):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT e.id,e.reading_id AS readingId,e.kind,e.level,e.received AS receivedAt,d.value,d.threshold,d.unit FROM events e LEFT JOIN event_details d ON d.event_id=e.id WHERE e.station=? AND e.source=? AND e.id<? ORDER BY e.id DESC LIMIT ?',
                    (station, source, before, limit)).fetchall()]

    def last_received(self, station, source):
        with self.connect() as db:
            row = db.execute('SELECT MAX(received) AS received FROM readings WHERE station=? AND source=?', (station, source)).fetchone()
            return row['received']

