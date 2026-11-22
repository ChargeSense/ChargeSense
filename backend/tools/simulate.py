"""Simulador HTTP: telemetria demonstrativa de uma estação de recarga EV."""
import argparse
import json
import math
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone


def make_payload(boot_id, sequence, uptime_ms):
    # Valores plausíveis para a bancada de demonstração: rede monofásica 220 V.
    voltage = round(220.0 + 0.8 * math.sin(sequence / 7), 2)
    current = round(15.5 + 1.0 * math.sin(sequence / 5), 2)
    temperature = round(32.0 + 1.5 * math.sin(sequence / 11), 2)
    power = round(voltage * current * 0.95, 2)
    return {'schemaVersion': 1, 'stationId': os.getenv('CHARGESENSE_STATION_ID', 'bancada-01'),
            'bootId': boot_id, 'sequence': sequence, 'source': 'simulated',
            'measuredAt': datetime.now(timezone.utc).isoformat(), 'uptimeMs': uptime_ms,
            'quality': 'valid', 'measurements': {'voltageV': voltage, 'currentA': current,
            'activePowerW': power, 'panelTempC': temperature}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--interval', type=float, default=2)
    args = parser.parse_args()
    if args.count < 1 or args.interval <= 0:
        parser.error('count e interval devem ser positivos')
    key = os.environ['CHARGESENSE_DEVICE_KEY']
    boot, start = str(uuid.uuid4()), time.monotonic()
    for sequence in range(args.count):
        payload = make_payload(boot, sequence, int((time.monotonic()-start)*1000))
        data = json.dumps(payload, allow_nan=False).encode()
        # Retransmissao usa exatamente a mesma identidade e o mesmo corpo.
        for attempt in range(3):
            request = urllib.request.Request(args.url.rstrip('/')+'/api/v1/telemetry', data=data,
                headers={'Content-Type': 'application/json', 'X-API-Key': key})
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    print(response.status, response.read().decode())
                break
            except urllib.error.HTTPError as error:
                if error.code < 500 or attempt == 2:
                    raise
                time.sleep(2 ** attempt)
            except urllib.error.URLError:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        if sequence + 1 < args.count:
            time.sleep(args.interval)


if __name__ == '__main__':
    main()
