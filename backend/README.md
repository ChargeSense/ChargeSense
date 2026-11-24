# API local ChargeSense

**ESP32/simulador → Wi-Fi/HTTP → FastAPI → SQLite → ChargeSense Mobile.** A API recebe telemetria e fornece consultas autenticadas. Não cria recursos AWS nem executa comandos no quadro.

## Executar

Python 3.12. No PowerShell, a partir da raiz do repositório:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
# Preencha as chaves e os limites antes de iniciar.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

O backend carrega automaticamente `backend/.env`. Copie para ele as mesmas chaves já usadas pelo Wokwi/ESP32 e aplicativo, e seus limites atuais. Chaves distintas com pelo menos 24 caracteres; o exemplo deixa ambas vazias para não fornecer credenciais padrão. O arquivo real fica ignorado pelo Git.

Nas próximas execuções basta, dentro de `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Reinicie o backend após editar o arquivo. Variáveis já definidas no terminal/sistema têm prioridade sobre o `.env`; use um novo terminal sem os antigos comandos `$env:...` para evitar valores antigos. O `.env` do aplicativo continua separado, em `chargesense-mobile/.env`. Nunca coloque a chave de dispositivo ou o token privado Expo em variáveis `EXPO_PUBLIC_*`.

O túnel Cloudflare continua sendo iniciado separadamente. Sua URL temporária pode mudar; nesse caso atualize o Wokwi e o endereço/registro de notificações no aplicativo.

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

Eventos são gerados em mudanças de nível confirmadas. Há histerese e confirmação temporal opcionais; `CHARGESENSE_ALERT_HOLD_SECONDS=0` confirma na primeira leitura. Push é enviado em agravamentos e no retorno ao normal. A API não aciona relé nem substitui futura lógica local de segurança.

## Testar

```sh
python -m unittest discover -s tests -v
```

## Migração futura

O contrato JSON v1 pode ser mantido em uma futura ingestão MQTT/AWS IoT Core. A persistência SQLite é local e não é proposta de banco distribuído. A migração exige provisionamento, identidade, TLS, retenção, limites de taxa e observabilidade.

## Cloudflare Tunnel

Precisa rodar o código no cmd na pasta fonte onde está o cloudflared.exe -> .\cloudflared.exe tunnel --url http://127.0.0.1:8000

## Alertas de tensão e corrente (app aberto)

Os limites de sobretensão e sobrecorrente são opcionais e configurados no terminal
que inicia o backend. Cada lista contém atenção, alerta e crítico, nessa ordem.
Sem a variável correspondente, a regra fica desativada. Não há limites elétricos
universais embutidos nem comando de desligamento.

Exemplo **exclusivamente demonstrativo para o Wokwi de 0–12 V / 22 ohms**:

```powershell
$env:CHARGESENSE_CURRENT_LEVELS = "0.30,0.40,0.50"
$env:CHARGESENSE_VOLTAGE_LEVELS = "7,9,11"
$env:CHARGESENSE_CURRENT_HYSTERESIS = "0.02"
$env:CHARGESENSE_VOLTAGE_HYSTERESIS = "0.3"
$env:CHARGESENSE_ALERT_HOLD_SECONDS = "0"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Mantenha as chaves de dispositivo e leitura já configuradas. Reinicie o backend
após mudar as variáveis. Histerese e permanência têm padrão zero para preservar
compatibilidade; configure-as como acima para evitar oscilações. As margens são
em A e V. Para descer de nível, a leitura deve ficar abaixo do limite menos a
margem. A permanência vale para todas as transições e é medida pelo recebimento;
um intervalo maior que 15 s, reinicialização do emissor, leitura inválida ou
valor ausente interrompe a confirmação pendente. Pacotes com medição mais de
15 s antiga não alteram alertas; sem horário sincronizado, use measuredAt=null.

Todas as mudanças confirmadas geram eventos dentro do app. Apenas subidas de nível
e retorno ao normal geram push. Histerese e permanência são preservadas. Tensão e corrente são independentes. Estado e eventos ficam na mesma
transação SQLite e separados por estação/origem. Duplicatas e sequências antigas
do mesmo boot não repetem nem alteram alertas. O banco existente recebe novas
tabelas automaticamente, sem apagar leituras. Alterar a configuração reinicia
a avaliação daquela regra na próxima leitura; eventos antigos são preservados.
Diagnósticos de qualidade continuam sendo registrados por leitura.

No app, selecione Backend local e Simulador. Após a primeira consulta estabelecer
a referência, eventos novos mostram um banner dispensável em qualquer aba.
O banner mostra o evento mais recente dentre os retornados; todos ficam na aba
Eventos. O app consulta os últimos 30 eventos a cada 5 s: não é uma fila de
entrega garantida. Reabrir/trocar origem não dispara avisos antigos. Para push com Android fechado, siga chargesense-mobile/PUSH_SETUP.md.
Banners e push têm fluxos de entrega separados.

Teste manual: conecte o app primeiro; varie 5 → 8 → 10 → 12 → 5 V no Wokwi,
mantendo cada patamar por pelo menos 10 s. Confira eventos das duas grandezas,
valor/limite/unidade, ausência de repetição no mesmo patamar e recuperação.
Pare o backend: o app deve mostrar falha sem manter o status online anterior.

## Horário do simulador

Para source=simulated, measuredAt ausente/null, inválido, sem fuso ou mais de
30 segundos no futuro recebe o horário UTC do backend no primeiro recebimento.
GET latest/readings expõem esse horário em measuredAt e timestampSource=backend.
Horários válidos são preservados (timestampSource=device), inclusive atrasados:
não é possível distinguir atraso de rede de relógio atrasado com segurança.
Para usar sempre o relógio do backend no Wokwi, envie measuredAt=null.
O computador do backend deve estar com data/hora sincronizadas.

Retransmissões mantêm o horário e ID originais e não repetem alertas.
A origem sensor mantém as validações anteriores; sem horário, timestampSource
é unknown. Outros erros de payload continuam retornando 422. Não há alteração
retroativa de leituras antigas nem necessidade de apagar o banco.

## Push Android

Consulte [configuração de push](../chargesense-mobile/PUSH_SETUP.md). O backend
inicia automaticamente o worker da fila. Nenhum envio ocorre sem um celular
cadastrado. Instale requirements.txt após atualizar.
