import hmac
import json
import math
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.security import APIKeyHeader
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from .models import Telemetry
from .store import Conflict, Store

key_header = APIKeyHeader(name='X-API-Key', auto_error=False)


def utcnow():
    return datetime.now(timezone.utc)


def create_app(db_path=None, device_key=None, read_key=None, station=None, levels=None, now=utcnow):
    @asynccontextmanager
    async def lifespan(app):
        write = device_key or os.getenv('CHARGESENSE_DEVICE_KEY', '')
        read = read_key or os.getenv('CHARGESENSE_READ_KEY', '')
        if len(write) < 24 or len(read) < 24 or write == read:
            raise RuntimeError('Configure chaves distintas CHARGESENSE_DEVICE_KEY e CHARGESENSE_READ_KEY com pelo menos 24 caracteres')
        configured_levels = levels
        if configured_levels is None:
            raw = os.getenv('CHARGESENSE_CURRENT_LEVELS', '')
            configured_levels = tuple(float(x) for x in raw.split(',')) if raw else ()
        if configured_levels and (len(configured_levels) != 3 or
                not all(math.isfinite(x) and x > 0 for x in configured_levels) or
                not configured_levels[0] < configured_levels[1] < configured_levels[2]):
            raise RuntimeError('CHARGESENSE_CURRENT_LEVELS exige tres limites positivos crescentes')
        app.state.device_key, app.state.read_key = write, read
        app.state.station = station or os.getenv('CHARGESENSE_STATION_ID', 'bancada-01')
        app.state.levels = configured_levels
        app.state.store = Store(db_path or os.getenv('CHARGESENSE_DB', str(Path(__file__).resolve().parents[1] / 'data' / 'chargesense.db')))
        yield

    app = FastAPI(title='ChargeSense API local', version='1.0.0', lifespan=lifespan,
                  description='Telemetria local. Sem comandos de corte. Grandezas indisponiveis usam null.')

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Nao devolver dados de entrada ou NaN/Infinity no corpo de erros.
        return JSONResponse({'detail': [
            {'loc': list(e['loc']), 'msg': e['msg'], 'type': e['type']}
            for e in error.errors()]}, status_code=422)

    # Limita o corpo inclusive quando enviado em chunks, sem confiar em Content-Length.
    @app.middleware('http')
    async def body_limit(request: Request, call_next):
        if request.method == 'POST':
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 8192:
                    return JSONResponse({'detail': 'Corpo excede 8192 bytes'}, status_code=413)
            request._body = bytes(body)
            try:
                def invalid_constant(value):
                    raise ValueError('Constante JSON nao finita')
                json.loads(body, parse_constant=invalid_constant)
            except (ValueError, UnicodeError):
                return JSONResponse({'detail': 'JSON invalido'}, status_code=422)
        return await call_next(request)

    def authorize(expected, supplied):
        if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(401, 'Chave ausente ou invalida')

    def device_auth(request: Request, key=Depends(key_header)):
        authorize(request.app.state.device_key, key)

    def read_auth(request: Request, key=Depends(key_header)):
        authorize(request.app.state.read_key, key)

    def check_station(station_id):
        if station_id != app.state.station:
            raise HTTPException(404, 'Estacao nao configurada')

    @app.get('/health', tags=['Operacao'])
    def health():
        return {'status': 'ok', 'service': 'chargesense-api', 'schemaVersion': 1}

    @app.post('/api/v1/telemetry', tags=['Dispositivo'], dependencies=[Depends(device_auth)])
    def ingest(payload: Telemetry, response: Response):
        check_station(payload.stationId)
        received = now()
        if payload.measuredAt and (payload.measuredAt - received).total_seconds() > 30:
            raise HTTPException(422, 'Horario de medicao mais de 30 segundos no futuro')
        event = None
        if payload.quality != 'valid':
            event = ('measurement_' + payload.quality, 'diagnostic')
        elif payload.measurements.currentA is not None and app.state.levels:
            value = payload.measurements.currentA
            for bound, level in reversed(list(zip(app.state.levels, ('attention', 'alert', 'critical')))):
                if value >= bound:
                    event = ('current_threshold', level)
                    break
        try:
            reading, duplicate = app.state.store.insert(payload, received.isoformat(timespec='microseconds'), event)
        except Conflict as error:
            raise HTTPException(409, str(error)) from error
        response.status_code = 200 if duplicate else 201
        return {'id': reading['id'], 'duplicate': duplicate, 'receivedAt': reading['receivedAt']}

    @app.get('/api/v1/stations/{station_id}/latest', tags=['Consulta'], dependencies=[Depends(read_auth)])
    def latest(station_id: str, source: Literal['sensor', 'simulated'] = 'sensor'):
        check_station(station_id)
        reading = app.state.store.latest(station_id, source)
        if reading is None:
            raise HTTPException(404, 'Nenhuma leitura para esta origem')
        return reading

    @app.get('/api/v1/stations/{station_id}/readings', tags=['Consulta'], dependencies=[Depends(read_auth)])
    def history(station_id: str, source: Literal['sensor', 'simulated'] = 'sensor',
                limit: int = Query(50, ge=1, le=500), before_id: int = Query(9223372036854775807, gt=0, le=9223372036854775807)):
        check_station(station_id)
        rows = app.state.store.history(station_id, source, limit, before_id)
        return {'items': rows, 'nextBeforeId': rows[-1]['id'] if len(rows) == limit else None}

    @app.get('/api/v1/stations/{station_id}/events', tags=['Consulta'], dependencies=[Depends(read_auth)])
    def events(station_id: str, source: Literal['sensor', 'simulated'] = 'sensor',
               limit: int = Query(50, ge=1, le=500), before_id: int = Query(9223372036854775807, gt=0, le=9223372036854775807)):
        check_station(station_id)
        rows = app.state.store.events(station_id, source, limit, before_id)
        return {'items': rows, 'nextBeforeId': rows[-1]['id'] if len(rows) == limit else None}

    @app.get('/api/v1/stations/{station_id}/status', tags=['Consulta'], dependencies=[Depends(read_auth)])
    def status(station_id: str, source: Literal['sensor', 'simulated'] = 'sensor'):
        check_station(station_id)
        reading = app.state.store.latest(station_id, source)
        last = app.state.store.last_received(station_id, source)
        receipt_age = max(0, (now() - datetime.fromisoformat(last)).total_seconds()) if last else None
        age = max(0, (now() - datetime.fromisoformat(reading['measuredAt'].replace('Z', '+00:00'))).total_seconds()) if reading and reading['measuredAt'] else None
        return {'stationId': station_id, 'source': source,
                'connection': 'never_seen' if last is None else 'online' if receipt_age <= 15 else 'offline',
                'lastReceivedAt': last, 'secondsSinceReception': receipt_age,
                'measurementAgeSeconds': age, 'freshness': 'unknown' if age is None else 'fresh' if age <= 15 else 'stale',
                'quality': reading['quality'] if reading else None,
                'thresholdsConfigured': bool(app.state.levels)}

    return app


app = create_app()
