#include <stdio.h>
#include <math.h>
#include <stdbool.h>
#include "sdkconfig.h"
#include "esp_err.h"
#include "esp_attr.h"
#include "esp_adc/adc_continuous.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "soc/soc_caps.h"
#include "measurement.h"
#include "config.h"
#include "telemetry.h"
#if !CONFIG_IDF_TARGET_ESP32
#error "Este projeto exige ESP32 classico; adapte canais/formato para outros chips."
#endif
static volatile bool overflow;
static measurement_t measurement;
static bool IRAM_ATTR on_overflow(adc_continuous_handle_t h,
        const adc_continuous_evt_data_t *e, void *u) {
    (void)h; (void)e; (void)u; overflow = true; return false;
}
static void halt(adc_continuous_handle_t adc, const char *reason) {
    adc_continuous_stop(adc);
    printf("# FALHA: %s. Coleta interrompida; corrigir e reiniciar.\n", reason);
    for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
}
void app_main(void) {
    telemetry_init();
#if CONFIG_CHARGESENSE_SIMULATE
    /* Testar rede/API sem sensores. Jamais rotular como leitura real. */
    unsigned sample = 0;
    for (;;) {
        double current = 0.5 + 0.2 * sin(sample++ / 5.0);
        telemetry_submit(12.0, current, 12.0 * current, NAN, "valid", true);
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
#endif
    if (!isfinite(SENSOR_PHASE_SAMPLES) || fabs(SENSOR_PHASE_SAMPLES) > 20 ||
        VOLTS_PER_COUNT < 0 || AMPS_PER_COUNT < 0 ||
        !isfinite(VOLTS_PER_COUNT) || !isfinite(AMPS_PER_COUNT) ||
        fabs(CURRENT_SIGN) != 1.0) {
        printf("# Configuracao invalida\n"); return;
    }
    adc_continuous_handle_t adc = NULL;
    adc_continuous_handle_cfg_t hcfg = {
        .max_store_buf_size = 32768, .conv_frame_size = 1024
    };
    ESP_ERROR_CHECK(adc_continuous_new_handle(&hcfg, &adc));
    /* GPIO34 = ADC1_CH6 (V); GPIO35 = ADC1_CH7 (I). */
    adc_digi_pattern_config_t pattern[2] = {
        {.atten=ADC_ATTEN_DB_12, .channel=6, .unit=ADC_UNIT_1, .bit_width=12},
        {.atten=ADC_ATTEN_DB_12, .channel=7, .unit=ADC_UNIT_1, .bit_width=12}
    };
    adc_continuous_config_t cfg = {
        .sample_freq_hz=SAMPLE_RATE_TOTAL, .conv_mode=ADC_CONV_SINGLE_UNIT_1,
        .format=ADC_DIGI_OUTPUT_FORMAT_TYPE1, .pattern_num=2, .adc_pattern=pattern
    };
    ESP_ERROR_CHECK(adc_continuous_config(adc, &cfg));
    adc_continuous_evt_cbs_t cb = {.on_pool_ovf=on_overflow};
    ESP_ERROR_CHECK(adc_continuous_register_event_callbacks(adc, &cb, NULL));
    printf("# ADC bruto: ganhos zero produzem nan em unidades fisicas.\n");
    printf("# P/FP sao estimativas ate validacao de ganho/fase; sem controle de rele.\n");
    printf("janela,t_s_nominal,vr_counts,ir_counts,v_offset,i_offset,v_min,v_max,i_min,i_max,Vrms,Irms,S_VA,P_est_W,FP_est,E_Wh_validos,clips,status\n");
    ESP_ERROR_CHECK(adc_continuous_start(adc));
    uint8_t buf[1024] __attribute__((aligned(4)));
    bool have_v = false;
    double v = 0, energy = 0;
    unsigned long window = 0;
    for (;;) {
        uint32_t len = 0;
        esp_err_t err = adc_continuous_read(adc, buf, sizeof(buf), &len, 1000);
        if (overflow) halt(adc, "overflow DMA, amostras perdidas");
        if (err != ESP_OK) halt(adc, "erro/timeout ADC");
        if (len % SOC_ADC_DIGI_RESULT_BYTES) halt(adc, "frame incompleto");
        for (uint32_t j=0; j<len; j+=SOC_ADC_DIGI_RESULT_BYTES) {
            const adc_digi_output_data_t *p = (const void *)&buf[j];
            unsigned ch = p->type1.channel;
            double raw = p->type1.data;
            if (ch == 6 && !have_v) { v = raw; have_v = true; }
            else if (ch == 7 && have_v) {
                have_v = false;
                result_t r;
                if (!measurement_push(&measurement, v, raw, &r)) continue;
                if (overflow) halt(adc, "overflow DMA");
                bool calibrated = AMPS_PER_COUNT > 0;
                double vr = VOLTAGE_CHANNEL_ENABLED && VOLTS_PER_COUNT > 0 ? r.vr*VOLTS_PER_COUNT : NAN;
                double ir = AMPS_PER_COUNT > 0 ? r.ir*AMPS_PER_COUNT : NAN;
                double ipeak = fmax(fabs(r.imin-r.imean), fabs(r.imax-r.imean))*AMPS_PER_COUNT;
                bool current_ok = calibrated && !r.iclips && r.ir >= MIN_RMS_COUNTS && ipeak <= CURRENT_SENSOR_PEAK_AMPS;
                bool voltage_ok = VOLTAGE_CHANNEL_ENABLED && VOLTS_PER_COUNT > 0 && !r.vclips && r.vr >= MIN_RMS_COUNTS;
                bool good = current_ok && voltage_ok;
                double apparent = good ? vr*ir : NAN;
                double power = good ? r.covariance*VOLTS_PER_COUNT*AMPS_PER_COUNT*CURRENT_SIGN : NAN;
                double pf = good && apparent > 0 ? power/apparent : NAN;
                double seconds = (double)WINDOW_PAIRS/PAIR_RATE;
                if (good && POWER_VALIDATED) energy += power*seconds/3600.0;
                const char *status = r.iclips ? "RECORTE_ADC_CORRENTE" : !calibrated ? "SEM_CALIBRACAO" :
                    ipeak > CURRENT_SENSOR_PEAK_AMPS ? "FORA_FAIXA_ACS712" : !current_ok ? "SINAL_BAIXO_OU_AUSENTE" :
                    !VOLTAGE_CHANNEL_ENABLED ? "CORRENTE_APENAS" : !good ? "TENSAO_INVALIDA" :
                    POWER_VALIDATED ? "VALIDADO_PELO_USUARIO" : "P_FP_NAO_VALIDADOS";
                /* API recebe somente valores aceitos, nao nan JSON ou estimativas de P. */
                const char *quality = !calibrated ? "uncalibrated" : current_ok ? "valid" : "invalid";
                telemetry_submit(current_ok && voltage_ok ? vr : NAN, current_ok ? ir : NAN,
                    good && POWER_VALIDATED ? power : NAN, NAN, quality, false);
                ++window;
                printf("%lu,%.3f,%.4f,%.4f,%.2f,%.2f,%.0f,%.0f,%.0f,%.0f,%.4f,%.5f,%.4f,%.4f,%.5f,%.7f,%u,%s\n",
                    window, window*seconds, r.vr,r.ir,r.vmean,r.imean,r.vmin,r.vmax,r.imin,r.imax,
                    vr,ir,apparent,power,pf,POWER_VALIDATED ? energy : NAN,r.clips,status);
            } else halt(adc, "sequencia inesperada de canais");
        }
    }
}

