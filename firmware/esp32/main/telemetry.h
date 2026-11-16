#pragma once
#include <stdbool.h>
void telemetry_init(void);
/* Nao bloqueia aquisicao. Valores indisponiveis: NAN. */
void telemetry_submit(double voltage, double current, double power,
                      double temperature, const char *quality, bool simulated);
