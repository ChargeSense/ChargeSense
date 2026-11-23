# API local ChargeSense

**ESP32/simulador → Wi-Fi/HTTP → FastAPI → SQLite → ChargeSense Mobile.** A API recebe telemetria e fornece consultas autenticadas. Não cria recursos AWS nem executa comandos no quadro.

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

Chaves privadas, diferentes, mínimo 24 caracteres. Sem chave padrão. Não gerar novas se a API continua com as antigas.

- Documentação interativa: http://127.0.0.1:8000/docs
- Saúde: http://127.0.0.1:8000/health
- Banco persistente: `backend/data/chargesense.db`

## Simular sem placa

Com a API rodando, abra outro terminal, defina a mesma chave de dispositivo e execute dentro de `backend`:

```powershell
$env:CHARGESENSE_DEVICE_KEY = "COLE_A_MESMA_CHAVE_DO_TERMINAL_DA_API"
python tools/simulate.py --count 60 --interval 2
```

O simulador envia `source=simulated` e grandezas fictícias plausíveis para a bancada EV: tensão próxima de 220 V, corrente próxima de 15,5 A, potência ativa calculada com fator de potência estimado de 0,95 e temperatura do quadro próxima de 32 °C. Esses números são apenas dados demonstrativos, não limites de segurança nem medições reais.

## Conectar o aplicativo

No app, selecione **Configurações → Backend local**.

- Emulador Android padrão: `http://10.0.2.2:8000`.
- Celular físico: reinicie o servidor com `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`, descubra o IPv4 LAN do computador (`ipconfig` no Windows) e informe `http://IP_DO_PC:8000` no app.
- Informe a mesma `CHARGESENSE_READ_KEY` usada no terminal da API.
- Selecione `Simulador` para os dados do script acima ou `Sensores` para telemetria enviada pelo ESP32.

Liberar a porta TCP 8000 somente na rede privada do firewall se necessário. Não abrir acesso pelo roteador à internet. Redes de convidados podem impedir comunicação entre dispositivos.

**Atenção:** HTTP local transmite a chave em claro. Use somente em rede confiável de laboratório. AWS/produção deve usar TLS e identidades individuais, não a chave compartilhada deste protótipo.

## Eventos e configuração

Ver [contrato](CONTRACT.md). Consultas usam `X-API-Key` com chave de leitura. Ingestão usa a chave de dispositivo. `stationId` padrão: `bancada-01`.

Limites de corrente ficam desabilitados por padrão. Para testar eventos com o simulador, configure três valores RMS crescentes em ampères antes de iniciar a API, por exemplo `15,16,17` (atenção, alerta, crítico) e reinicie o processo. São valores fictícios para teste de software, não parâmetros de proteção física.

Cada leitura acima do limite gera evento. Ainda não há histerese, agrupamento de incidentes ou notificações push nesta versão. A API não aciona relé nem substitui futura lógica local de segurança.

## Testar

```sh
python -m unittest discover -s tests -v
```

## Migração futura

O contrato JSON v1 pode ser mantido em uma futura ingestão MQTT/AWS IoT Core. A persistência SQLite é local e não é proposta de banco distribuído. A migração exige provisionamento, identidade, TLS, retenção, limites de taxa e observabilidade.

## Cloudflare Tunnel

Precisa rodar o código no cmd na pasta fonte onde está o cloudflared.exe -> .\cloudflared.exe tunnel --url http://127.0.0.1:8000