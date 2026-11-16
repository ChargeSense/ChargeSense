# Firmware ESP32 — ChargeSense

ESP32 clássico de 38 pinos, ESP-IDF **5.2.5**, linguagem C. Comunicação: ESP32 → Wi-Fi/HTTP → API local. USB continua disponível para diagnóstico CSV. Não há acionamento de relé ou comandos remotos implementados.

## Hardware e limites

- Corrente: **ACS712-30A**, não SCT-013. A carga passa pelos dois bornes em série. OUT é apenas sinal. Alimentação nominal do chip: 5 V DC; offset VCC/2 e sensibilidade típica 66 mV/A. Não aplicar a antiga polarização do SCT.
- OUT exige condicionamento validado antes do GPIO35. O dimensionamento está pendente: não conectar diretamente por suposição. Correntes pequenas podem ter relação sinal/ruído ruim nesta versão.
- Tensão: a foto mostra divisor resistivo sem isolamento, não ZMPT101B. **Não conectar diretamente à fonte AC/ADC.** `VOLTAGE_CHANNEL_ENABLED=0` por padrão. GPIO34 é reservado; desconectado do sensor, pode ficar no GND da eletrônica para não flutuar. Não ligar terminal AC ao GND por inferência.
- Fonte: 10–30 V AC informados, mas modelo, isolamento, frequência e corrente máxima pendentes. 30 V RMS senoidais têm pico de aproximadamente 42,4 V.
- Temperatura: modelo desconhecido, valor enviado null; não presumir pinagem.
- 30 A é a faixa nominal de pico do sensor, não a capacidade autorizada da bancada. Potência fora do protoboard; proteções, carga e fios precisam de dimensionamento. As instruções antigas de ZMPT/SCT não se aplicam aos módulos fotografados.

## Teste sem sensores

Iniciar a API conforme [backend/README.md](../../backend/README.md). Na raiz do repositório, em terminal ESP-IDF:

```sh
cd firmware/esp32
idf.py set-target esp32
idf.py menuconfig
```

Em **ChargeSense API local**, habilitar envio HTTP e **Gerar dados simulados sem ler os sensores**. Preencher SSID/senha, stationId `bancada-01`, chave de dispositivo da API e URL completa, por exemplo `http://192.168.1.20:8000/api/v1/telemetry`. Usar o IP LAN do computador, nunca localhost. Rede 2,4 GHz WPA2/WPA3 compatível, sem isolamento entre clientes.

```sh
idf.py build
idf.py -p COM5 flash monitor
```

Trocar COM5 pela porta real. O simulador não inicializa ADC. Envia a cada 2 s valores fictícios de 12 V, aproximadamente 0,3–0,7 A, potência resistiva e temperatura null; origem sempre `simulated`. Consultar latest/status com `?source=simulated` e chave de leitura.

SSID, senha e token ficam no sdkconfig ignorado pelo Git e no binário da placa: não publicar binários configurados com credenciais. HTTP transmite dados/chave em claro e é apenas para rede confiável de laboratório. HTTPS é aceito com verificação pelo bundle de certificados ESP-IDF; não há bypass TLS. Para internet/AWS, configurar identidade individual e TLS.

## Aquisição física, após validar a montagem

Desabilitar simulação. ADC1 solicita 20.000 conversões/s alternando GPIO34/35 (10.000 por canal). Janelas de 1 s removem offset e calculam RMS. O ADC ainda amostra tensão, mas o canal desabilitado e seus erros não interferem na validação da corrente. API envia tensão/potência null nessa configuração.

Ganhos em `main/config.h` começam em zero. A API recebe `quality=uncalibrated` e grandezas null até calibrar. Para corrente AC: `AMPS_PER_COUNT = corrente_RMS_referencia / ir_counts`. Validar em três ou mais patamares, incluindo o menor sinal útil. O ganho inclui sensor, condicionamento e ADC. `MIN_RMS_COUNTS` é apenas limiar inicial de ruído; sinal baixo é indeterminado, não confirmação de zero ou de corte. Os picos são comparados à faixa do ACS712; nem toda saturação interna é detectável pelo software.

Só habilitar tensão após reprojetar/validar seu circuito e calibrar `VOLTS_PER_COUNT`. Potência exige ambos os canais e validação de fase; API só publica P com `POWER_VALIDATED=1`. Interpolação é aproximada; taxa, ruído e exatidão precisam de teste físico. Energia permanece apenas no CSV, somando janelas válidas sem persistência após reinício. Não é medidor certificado nem proteção elétrica.

## Comunicação e falhas

- Enfileiramento sem bloquear aquisição; tarefa separada faz POST. Fila de 8 mensagens em RAM; cheia descarta a nova leitura com aviso. Até três tentativas por mensagem com corpo/id iguais, depois descarte. Sem persistência offline ou garantia de entrega nesta versão.
- Timeout HTTP 3 s; espera de Wi-Fi por tentativa até 5 s; backoff limitado e reconexão Wi-Fi. Redirecionamentos HTTP desabilitados para não encaminhar chaves.
- UUID por boot e sequence crescente deduplicam reenvios. SNTP usa servidor configurável; sem sincronismo measuredAt=null e frescor desconhecido. Uptime sempre enviado. Timestamp marca o processamento da janela em segundos, não cada amostra.
- Overflow/timeout ADC interrompe aquisição até reinício; após cessarem mensagens a API indica offline. O transporte não implementa a futura lógica local de desligamento.

## Testes

```sh
gcc -std=c11 -Wall -Wextra -Werror -I main main/measurement.c tests/test_measurement.c -lm -o /tmp/test_measurement
/tmp/test_measurement
```

CI executa cálculos e compila três perfis: offline, HTTP com ADC e simulador HTTP. Isso não valida Wi-Fi/sensores na placa. Não houve ensaio físico nesta implementação.

Referências: [ACS712](https://www.allegromicro.com/-/media/files/datasheets/acs712-datasheet.pdf), [ADC](https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32/api-reference/peripherals/adc_continuous.html), [HTTP ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/v5.2.5/esp32/api-reference/protocols/esp_http_client.html).
