# API local ChargeSense

**ESP32 → Wi-Fi/HTTP → FastAPI → SQLite → consultas do software.** O aplicativo existente não foi alterado; a interface será integrada depois. Não cria recursos AWS nem executa comandos no quadro.

## Executar

Python 3.12. No PowerShell, a partir da raiz do repositório:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:CHARGESENSE_DEVICE_KEY = (python -c "import secrets; print(secrets.token_hex(24))")
$env:CHARGESENSE_READ_KEY = (python -c "import secrets; print(secrets.token_hex(24))")
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Linux/macOS, na pasta backend:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
export CHARGESENSE_DEVICE_KEY="$(python -c 'import secrets; print(secrets.token_hex(24))')"
export CHARGESENSE_READ_KEY="$(python -c 'import secrets; print(secrets.token_hex(24))')"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Chaves privadas, diferentes, mínimo 24 caracteres. Sem chave padrão. Essas variáveis só existem no terminal e processos filhos: no segundo terminal, definir as MESMAS chaves por canal local privado. Não gerar novas se a API continua com as antigas. Não há leitura automática de .env.

- Documentação interativa: http://127.0.0.1:8000/docs
- OpenAPI: http://127.0.0.1:8000/openapi.json
- Saúde: http://127.0.0.1:8000/health

No Swagger, usar Authorize com chave de dispositivo para POST; trocar para chave de leitura para GET. Documentação/saúde são públicas; dados são autenticados. Banco persistente: `backend/data/chargesense.db`. `CHARGESENSE_DB` muda o caminho. Usar uma instância Uvicorn; SQLite não é proposta de persistência distribuída.

## Simular sem placa

Com API rodando e chave de dispositivo definida no segundo terminal, dentro de backend:

```sh
python tools/simulate.py --count 10 --interval 2
```

Dados fictícios de 12 V e aproximadamente 0,3–0,7 A, potência resistiva e temperatura null. Sempre source=simulated. Também há [simulador embarcado no ESP32](../firmware/esp32/README.md), que não lê sensores.

Consultar no PowerShell com chave de leitura:

```powershell
$headers = @{"X-API-Key" = $env:CHARGESENSE_READ_KEY}
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/stations/bancada-01/latest?source=simulated" -Headers $headers
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/stations/bancada-01/status?source=simulated" -Headers $headers
```

## Acesso na rede local

Reiniciar com `--host 0.0.0.0`. Descobrir IPv4 LAN do PC (ipconfig no Windows) e usar esse endereço no ESP32, por exemplo http://192.168.1.20:8000. Liberar porta TCP 8000 somente na rede privada do firewall se necessário; não abrir acesso pelo roteador à internet. PC/placa/telefone precisam se comunicar; redes de convidados podem impedir.

Localhost no celular/ESP32 é o próprio aparelho. No emulador Android padrão, o host costuma ser 10.0.2.2. O futuro app precisa de cliente HTTP, configuração de transporte de desenvolvimento e armazenamento seguro da chave de leitura; não colocar nele a chave de dispositivo. Não foram alterados arquivos mobile. Não há CORS global; futuro frontend web deverá autorizar apenas suas origens.

HTTP local transmite a chave em claro: usar apenas rede confiável de laboratório. AWS deve usar TLS e identidades por dispositivo/usuário, não o token compartilhado deste protótipo.

## Eventos e configuração

Ver [contrato](CONTRACT.md). Consultas podem ocorrer a cada 2 s; não há WebSocket nesta etapa. StationId padrão `bancada-01`, configurável em `CHARGESENSE_STATION_ID`.

Leituras inválidas/sem calibração geram eventos de diagnóstico. Limites de corrente ficam DESABILITADOS por padrão. Para testar software, configurar `CHARGESENSE_CURRENT_LEVELS` com três valores RMS em A positivos crescentes, por exemplo `0.4,0.5,0.6` para o simulador; reiniciar API. São valores fictícios, não parâmetros de proteção física.

Cada leitura acima do limite gera evento attention/alert/critical. Sem histerese, agrupamento de incidentes ou notificações push nesta versão. Simulação tem eventos separados. API não aciona relé nem substitui futura lógica local de corte.

## Testar

```sh
python -m unittest discover -s tests -v
```

Testes cobrem autenticação, origens, deduplicação concorrente, conflito, persistência, paginação, números inválidos, null, horários/ordem, offline e eventos. CI repete os testes.

## Migração AWS

Contrato JSON v1 pode ser mantido em ingestão MQTT/AWS IoT Core. `app/store.py` concentra a persistência a substituir por banco gerenciado; `models.py` valida dados; `main.py` reúne rotas e regras iniciais. Ainda exige provisionamento, identidade, TLS, retenção, limites de taxa e observabilidade.

Hoje histórico cresce sem retenção automática, chaves atendem uma estação, e fila embarcada não é persistente. Backup SQLite deve ser consistente com WAL; não copiar somente o arquivo principal com servidor ativo.
