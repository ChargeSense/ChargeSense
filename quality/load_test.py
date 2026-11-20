"""HTTP real local, servidor separado, banco descartavel. Nao usa infraestrutura externa."""
import concurrent.futures, json, math, os, platform, socket, subprocess, sys, tempfile, time, uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parent
BACKEND=ROOT.parent/'backend'
KEY='load-device-00000000000000000000'; READ='load-reader-00000000000000000000'
def main():
  with tempfile.TemporaryDirectory() as tmp:
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    env={**os.environ,'CHARGESENSE_DEVICE_KEY':KEY,'CHARGESENSE_READ_KEY':READ,'CHARGESENSE_DB':str(Path(tmp)/'load.db'),'CHARGESENSE_CURRENT_LEVELS':'1,2,3'}
    proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--workers','1'],cwd=BACKEND,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base=f'http://127.0.0.1:{port}'
    try:
      with httpx.Client(base_url=base,timeout=20,trust_env=False) as client:
        for _ in range(100):
          try:
            if client.get('/health').status_code==200: break
          except httpx.HTTPError: pass
          time.sleep(.1)
        else: raise RuntimeError('Servidor nao iniciou')
        results=[]
        for concurrency in (1,5,20,50):
          boot=str(uuid.uuid4());n=500
          def request(i):
            start=time.perf_counter()
            try:
              if i%2==0:
                p={'schemaVersion':1,'stationId':'bancada-01','bootId':boot,'sequence':i,'source':'simulated','uptimeMs':i,'quality':'valid','measurements':{'currentA':2.5}}
                r=client.post('/api/v1/telemetry',json=p,headers={'X-API-Key':KEY});expected=201
              else:
                r=client.get('/api/v1/stations/bancada-01/readings?source=simulated&limit=50',headers={'X-API-Key':READ});expected=200
              return (time.perf_counter()-start)*1000,r.status_code==expected,r.status_code
            except httpx.HTTPError:
              return (time.perf_counter()-start)*1000,False,'transport_error'
          start=time.perf_counter()
          with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool: rows=list(pool.map(request,range(n)))
          elapsed=time.perf_counter()-start;times=sorted(r[0] for r in rows)
          item={'concurrency':concurrency,'requests':n,'seconds':elapsed,'rps':n/elapsed,'mean_ms':sum(times)/n,'p50_ms':times[math.ceil(.5*n)-1],'p95_ms':times[math.ceil(.95*n)-1],'max_ms':max(times),'errors':sum(not r[1] for r in rows),'error_rate':sum(not r[1] for r in rows)/n}
          results.append(item);print(json.dumps(item),flush=True)
        output={'environment':{'python':sys.version,'platform':platform.platform(),'cpu_count':os.cpu_count(),'workers':1,'mix':'50% POST telemetry / 50% GET readings','warmup':'health readiness only','repeat':1,'database':'SQLite WAL cumulativo, temporario','transport':'TCP loopback HTTP'},'results':results}
        (ROOT/'evidence').mkdir(exist_ok=True)
        (ROOT/'evidence'/'load.json').write_text(json.dumps(output,indent=2))
    finally:
      proc.terminate();proc.wait(timeout=10)
if __name__=='__main__':main()
