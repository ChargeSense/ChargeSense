# Contrato de telemetria v1

`POST /api/v1/telemetry`, Content-Type application/json e X-API-Key com chave de dispositivo:

```json
{
  "schemaVersion": 1,
  "stationId": "bancada-01",
  "bootId": "8505ad41-ed6c-43e2-b190-f079e292bca8",
  "sequence": 0,
  "source": "sensor",
  "measuredAt": "2026-11-16T16:00:00Z",
  "uptimeMs": 1000,
  "quality": "valid",
  "measurements": {
    "voltageV": null,
    "currentA": 0.5,
    "activePowerW": null,
    "panelTempC": null
  }
}
```

Exemplo de formato: substituir horário/dados. Todos os campos de topo são obrigatórios exceto measuredAt, que pode ser null/omitido sem relógio sincronizado. Horários devem incluir fuso; mais de 30 s no futuro são rejeitados. Valores normalizados para UTC.

- source: sensor ou simulated. Consultas usam sensor por padrão; simulação não substitui dados reais.
- quality: valid, uncalibrated ou invalid. Nos dois últimos, grandezas devem ser null. Valid exige ao menos uma grandeza e significa validação pelo emissor, não certificação metrológica.
- Grandezas ausentes: null, nunca zero inventado ou NaN/Infinity. V/I são RMS não negativas; potência pode ter sinal e exige V/I preenchidas. Temperatura opcional.
- bootId: UUID novo a cada boot; sequence inteiro crescente. Reenvios mantêm identidade e corpo. uptimeMs é monotônico desde boot, não horário civil.
- Máximo 8192 bytes, campos extras rejeitados. Limites numéricos do schema não são limites de segurança elétrica.

Nova mensagem: 201 com id, duplicate=false, receivedAt. Reenvio idêntico: 200 com mesmo id/receivedAt. Mesmo (stationId,source,bootId,sequence) com outro conteúdo: 409. Chave inválida: 401; estação não configurada: 404; JSON/valores inválidos: 422; corpo grande: 413. Repetir falhas de transporte/5xx com backoff e corpo idêntico, não erros permanentes 4xx.

## Consultas

Chave de leitura no X-API-Key. Acrescentar `?source=simulated` para simulação.

| GET | Finalidade |
| --- | --- |
| /health | Saúde do processo, sem autenticação |
| /api/v1/stations/{id}/latest | Última leitura, 404 quando vazia |
| /api/v1/stations/{id}/readings | Histórico paginado |
| /api/v1/stations/{id}/events | Eventos paginados |
| /api/v1/stations/{id}/status | Conexão, frescor e qualidade |

Histórico/eventos: limit de 1 a 500 e cursor before_id. Resposta items e nextBeforeId; usar este último como próximo before_id. Ordem por id de ingestão decrescente; não por data de medição. Uma página final vazia é possível se a anterior tiver exatamente limit itens.

Latest seleciona maior sequence em cada boot, depois data de medição (ou recepção se desconhecida) entre boots. Sem relógio sincronizado, não é possível ordenar perfeitamente boots distintos atrasados.

Status.connection: never_seen, online ou offline; online = nova mensagem recebida nos últimos 15 s. Duplicatas não renovam conexão. Não comprova carga ligada ou Wi-Fi conectado neste instante.

Status.freshness: fresh/stale/unknown, pelo horário de medição e limiar de 15 s. Pacote atrasado pode indicar online com leitura stale. Sem measuredAt, frescor e idade desconhecidos. Futuro app deve mostrar horário e qualidade, sem transformar desconexão em zero.

Eventos: measurement_uncalibrated, measurement_invalid ou current_threshold. Incluem readingId, kind, level e receivedAt. São registros por leitura, não comandos de corte. Filtrados por source.


## Extensão de eventos de limites

`current_threshold` e `voltage_threshold` indicam aumentos de gravidade para níveis attention,
alert ou critical. `current_recovered` e `voltage_recovered` usam level `normal`.
Eventos novos de limites incluem `value`, `threshold` e `unit` (A/V). Em recuperação,
threshold é a fronteira de retorno (primeiro limite menos histerese). Eventos
antigos/diagnósticos podem ter esses campos null. Consumidores devem aceitar o
novo nível normal. thresholdsConfigured é true quando há regra de corrente OU
tensão. Eventos de limites agora são transições persistidas, não um evento por
leitura. Consulte o README para configuração, permanência e limites da entrega.

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

Reduções entre níveis de perigo não geram eventos; o estado é atualizado para
avaliar futuras subidas. O retorno ao normal gera recuperação.

## Cadastro push

POST /api/v1/stations/{station_id}/push-subscriptions, com chave de leitura.
Body: {"token":"ExponentPushToken[...]","source":"simulated","enabled":true}.
enabled=false remove a assinatura e os jobs pendentes. Um token tem uma origem
ativa por backend; atualizar muda essa origem sem enviar histórico.
A resposta expõe apenas enabled/source, nunca tokens de outros dispositivos.
