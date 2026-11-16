# Firmware ChargeSense

O firmware embarcado fica neste diretório; o aplicativo permanece em `chargesense-mobile/`, na raiz do mesmo repositório.

## Primeiro protótipo

- [ESP32 — código e guia de bancada](esp32/README.md)
- [Aquisição ADC e saída CSV](esp32/main/main.c)
- [Cálculos elétricos](esp32/main/measurement.c)
- [Parâmetros de calibração](esp32/main/config.h)
- [Testes numéricos](esp32/tests/test_measurement.c)

Plataforma: ESP32 clássico (WROOM/DevKit), C e ESP-IDF 5.2.5. A fonte foi informada como AC ajustável entre 10 e 30 V; modelo, frequência, isolamento e corrente máxima ainda precisam ser confirmados. O SCT-013-005 (5 A / 1 V) e o módulo ZMPT101B são premissas até conferir os componentes físicos.

No terminal ESP-IDF, a partir da raiz do repositório:

```sh
cd firmware/esp32
idf.py set-target esp32
idf.py build
idf.py -p COM5 flash monitor
```

Substituir COM5 pela porta real. A calibração é obrigatória: os ganhos começam em zero, gerando `nan` em unidades físicas ainda não calibradas. A integração atual é ESP32 → USB/serial → computador. Não há comunicação com o aplicativo, Wi-Fi ou acionamento do relé nesta etapa.

A workflow `ESP32 firmware` verifica os cálculos e compila o projeto. Passar na CI não comprova medição correta em hardware: ainda é necessário validar condicionamento, faixa, amostragem, ganho e fase na bancada.
