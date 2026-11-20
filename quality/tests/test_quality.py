import copy
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Telemetry

WRITE='qa-device-0000000000000000000000'
READ='qa-reader-0000000000000000000000'
BASE={'schemaVersion':1,'stationId':'bancada-01','bootId':'8505ad41-ed6c-43e2-b190-f079e292bca8','sequence':0,'source':'sensor','measuredAt':'2026-11-20T12:00:00Z','uptimeMs':1000,'quality':'valid','measurements':{'currentA':0.5}}
@pytest.fixture
def ctx(tmp_path):
    clock=Mock(return_value=datetime(2026,11,20,12,tzinfo=timezone.utc))
    app=create_app(tmp_path/'qa.db',WRITE,READ,levels=(1,2,3),now=clock)
    with TestClient(app) as client:
        yield client,clock,copy.deepcopy(BASE)
def post(c,p): return c.post('/api/v1/telemetry',json=p,headers={'X-API-Key':WRITE})
def get(c,path): return c.get('/api/v1/stations/bancada-01/'+path,headers={'X-API-Key':READ})

@pytest.mark.parametrize('field,value,code',[
 ('currentA',-0.001,422),('currentA',0,201),('currentA',0.001,201),('currentA',99999.999,201),('currentA',100000,201),('currentA',100000.001,422),
 ('voltageV',-0.001,422),('voltageV',0,201),('voltageV',100000,201),('voltageV',100000.001,422),
 ('panelTempC',-100.001,422),('panelTempC',-100,201),('panelTempC',-99.999,201),('panelTempC',199.999,201),('panelTempC',200,201),('panelTempC',200.001,422)])
def test_TC01_measurements(ctx,field,value,code):
    c,_,p=ctx;p['measurements'][field]=value
    assert post(c,p).status_code==code

@pytest.mark.parametrize('limit,code',[(0,422),(1,200),(2,200),(499,200),(500,200),(501,422),('abc',422)])
@pytest.mark.parametrize('route',['readings','events'])
def test_TC02_pagination(ctx,limit,code,route):
    c,_,p=ctx;post(c,p)
    assert get(c,f'{route}?limit={limit}').status_code==code

@pytest.mark.parametrize('quality,current,code,level',[
 ('valid',0.999,201,None),('valid',1,201,'attention'),('valid',1.001,201,'attention'),
 ('valid',1.999,201,'attention'),('valid',2,201,'alert'),('valid',2.001,201,'alert'),
 ('valid',2.999,201,'alert'),('valid',3,201,'critical'),('valid',3.001,201,'critical'),
 ('valid',None,422,None),('invalid',None,201,'diagnostic'),('uncalibrated',None,201,'diagnostic'),
 ('invalid',1,422,None),('uncalibrated',1,422,None)])
def test_TC03_decision(ctx,quality,current,code,level):
    c,_,p=ctx;p.update(quality=quality);p['measurements']['currentA']=current
    assert post(c,p).status_code==code
    events=get(c,'events').json()['items']
    assert [e['level'] for e in events]==([] if level is None else [level])

@pytest.mark.parametrize('age,state',[(14.999,'online'),(15,'online'),(15.001,'offline')])
def test_TC04_status_boundary(ctx,age,state):
    c,clock,p=ctx;post(c,p);clock.return_value+=timedelta(seconds=age)
    status=get(c,'status').json()
    assert status['connection']==state
    assert status['freshness']==('fresh' if state=='online' else 'stale')

@pytest.mark.parametrize('future,code',[(29.999,201),(30,201),(30.001,422)])
def test_TC05_future(ctx,future,code):
    c,clock,p=ctx;p['measuredAt']=(clock()+timedelta(seconds=future)).isoformat()
    assert post(c,p).status_code==code

@pytest.mark.parametrize('value,code',[(-1,422),(0,201),(1,201),(9007199254740990,201),(9007199254740991,201),(9007199254740992,422),(True,422),(1.5,422)])
@pytest.mark.parametrize('field',['sequence','uptimeMs'])
def test_TC06_integer(ctx,value,code,field):
    c,_,p=ctx;p[field]=value;assert post(c,p).status_code==code

@pytest.mark.parametrize('key,code',[(None,401),('wrong',401),(READ,401),(WRITE,201)])
def test_TC07_auth(ctx,key,code):
    c,_,p=ctx;assert c.post('/api/v1/telemetry',json=p,headers={} if key is None else {'X-API-Key':key}).status_code==code

@pytest.mark.parametrize('size,code',[(8191,201),(8192,201),(8193,413)])
def test_TC08_body(ctx,size,code):
    import json
    c,_,p=ctx;raw=json.dumps(p);raw+=' '*(size-len(raw.encode()))
    assert c.post('/api/v1/telemetry',content=raw,headers={'X-API-Key':WRITE,'Content-Type':'application/json'}).status_code==code

@pytest.mark.parametrize('field,value',[('source','manual'),('quality','bad'),('bootId','bad'),('stationId','a'*65),('stationId',''),('stationId','../x'),('schemaVersion',2)])
def test_TC09_invalid_classes(ctx,field,value):
    c,_,p=ctx;p[field]=value;assert post(c,p).status_code==422

def test_TC10_atomic_conflict(ctx):
    c,_,p=ctx;p['measurements']['currentA']=3
    a=post(c,p);b=post(c,p);p['measurements']['currentA']=4;d=post(c,p)
    assert [a.status_code,b.status_code,d.status_code]==[201,200,409]
    assert a.json()['id']==b.json()['id']
    assert len(get(c,'events').json()['items'])==1

def test_TC11_store_isolation(ctx,monkeypatch):
    c,_,_=ctx;mock=Mock(return_value=None)
    monkeypatch.setattr(c.app.state.store,'latest',mock)
    assert get(c,'latest').status_code==404
    mock.assert_called_once_with('bancada-01','sensor')

@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf')])
def test_TC12_unit_nonfinite(value):
    from pydantic import ValidationError
    p=copy.deepcopy(BASE);p['measurements']['currentA']=value
    with pytest.raises(ValidationError): Telemetry.model_validate(p)

@pytest.mark.parametrize('value',[True,'1.5'])
def test_TC13_numeric_coercion_characterization(ctx,value):
    c,_,p=ctx;p['measurements']['currentA']=value
    assert post(c,p).status_code==201  # Observacao: coercao atual, nao criterio de aceitacao.
    assert get(c,'latest').json()['measurements']['currentA']==float(value)

@pytest.mark.xfail(strict=True,reason='D-01: API converte boolean/string em corrente; criterio QA proposto exige numero JSON')
@pytest.mark.parametrize('value',[True,'1.5'])
def test_TC14_strict_numeric_proposed(ctx,value):
    c,_,p=ctx;p['measurements']['currentA']=value
    assert post(c,p).status_code==422

@pytest.mark.parametrize('levels',[(1,1,3),(-1,2,3),(1,2),(1,2,float('inf'))])
def test_TC15_bad_config(tmp_path,levels):
    with pytest.raises(RuntimeError):
        with TestClient(create_app(tmp_path/'x.db',WRITE,READ,levels=levels)): pass

def test_TC16_firmware_native(tmp_path):
    import subprocess
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    fw=root.parent/'firmware'/'esp32'
    exe=tmp_path/'measurement_test'
    subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-I',str(fw/'main'),str(fw/'tests'/'test_measurement.c'),str(fw/'main'/'measurement.c'),'-lm','-o',str(exe)],check=True,capture_output=True)
    result=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
    assert 'PASS: RMS' in result.stdout

def test_TC17_partial_measurement(ctx):
    c,_,p=ctx;p['measurements']={'voltageV':220,'currentA':None}
    assert post(c,p).status_code==201
    assert get(c,'events').json()['items']==[]
