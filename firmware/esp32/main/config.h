#pragma once
/* ESP32 classico (WROOM/DevKit), ESP-IDF 5.2. Nao usar em S3/C3 sem adaptar. */
#define SAMPLE_RATE_TOTAL 20000
#define PAIR_RATE (SAMPLE_RATE_TOTAL / 2)
#define WINDOW_PAIRS PAIR_RATE
/* Zero = nao calibrado. Obtidos com instrumento de referencia, NAO adivinhar. */
#define VOLTS_PER_COUNT 0.0
#define AMPS_PER_COUNT 0.0
/* Hardware confirmado: ACS712-30A. Limite de pico do sensor, NAO da bancada. */
#define CURRENT_SENSOR_PEAK_AMPS 30.0
/* Divisor de tensao fotografado nao pode ser ligado diretamente em AC.
   Habilitar somente depois de reprojetar e validar o condicionamento. */
#define VOLTAGE_CHANNEL_ENABLED 0
#define CURRENT_SIGN 1.0
/* Avanco adicional da tensao em periodos de 100 us. Limite +/-20.
   0.5 periodo do multiplexador ja e compensado no measurement.c.
   Ajustar fase com referencia; nao equivale a graus. */
#define SENSOR_PHASE_SAMPLES 0.0
/* Ativar SOMENTE apos validar ganhos, fase, taxa e potencia com instrumento. */
#define POWER_VALIDATED 0
/* Diagnostico digital grosseiro. Nao substitui validar faixa analogica. */
#define RAW_LOW 50
#define RAW_HIGH 4045
#define MIN_RMS_COUNTS 3.0

