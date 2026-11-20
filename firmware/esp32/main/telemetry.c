#include "telemetry.h"
#include "sdkconfig.h"
#if CONFIG_CHARGESENSE_HTTP_ENABLE
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_sntp.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs_flash.h"

static const char *TAG = "telemetry";
static QueueHandle_t queue;
static EventGroupHandle_t network;
static char boot_id[37];
static unsigned long sequence;
typedef struct { char json[768]; } message_t;

static void event_handler(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg; (void)data;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) esp_wifi_connect();
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(network, BIT0);
        esp_wifi_connect();
    }
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) xEventGroupSetBits(network, BIT0);
}

static void sender(void *arg) {
    (void)arg;
    message_t msg;
    for (;;) {
        if (xQueueReceive(queue, &msg, portMAX_DELAY) != pdTRUE) continue;
        bool delivered = false;
        for (int attempt = 0; attempt < 3; ++attempt) {
            if (!(xEventGroupWaitBits(network, BIT0, pdFALSE, pdTRUE, pdMS_TO_TICKS(5000)) & BIT0)) continue;
            esp_http_client_config_t cfg = {
                .url = CONFIG_CHARGESENSE_API_URL, .timeout_ms = 3000,
                .disable_auto_redirect = true, .crt_bundle_attach = esp_crt_bundle_attach
            };
            esp_http_client_handle_t client = esp_http_client_init(&cfg);
            if (!client) { vTaskDelay(pdMS_TO_TICKS(1000)); continue; }
            esp_http_client_set_method(client, HTTP_METHOD_POST);
            esp_http_client_set_header(client, "Content-Type", "application/json");
            esp_http_client_set_header(client, "X-API-Key", CONFIG_CHARGESENSE_DEVICE_KEY);
            esp_http_client_set_post_field(client, msg.json, strlen(msg.json));
            esp_err_t error = esp_http_client_perform(client);
            int code = esp_http_client_get_status_code(client);
            esp_http_client_cleanup(client);
            if (error == ESP_OK && (code == 200 || code == 201)) { delivered = true; break; }
            if (error == ESP_OK && code >= 400 && code < 500) {
                ESP_LOGE(TAG, "API rejeitou mensagem: HTTP %d (ver configuracao/contrato)", code);
                break;
            }
            vTaskDelay(pdMS_TO_TICKS(1000 * (1 << attempt)));
        }
        if (!delivered) ESP_LOGW(TAG, "Mensagem descartada apos falha; sem buffer persistente");
    }
}

void telemetry_init(void) {
    if (strlen(CONFIG_CHARGESENSE_DEVICE_KEY) < 24 || !strlen(CONFIG_CHARGESENSE_WIFI_SSID)) {
        ESP_LOGE(TAG, "Configure SSID e chave de pelo menos 24 caracteres; rede desabilitada");
        return;
    }
    esp_err_t error = nvs_flash_init();
    if (error == ESP_ERR_NVS_NO_FREE_PAGES || error == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGE(TAG, "NVS requer manutencao; nao apagado automaticamente"); return;
    }
    ESP_ERROR_CHECK(error);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    network = xEventGroupCreate();
    configASSERT(network);
    configASSERT(esp_netif_create_default_wifi_sta());
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, event_handler, NULL));
    wifi_config_t wifi = {0};
    snprintf((char *)wifi.sta.ssid, sizeof(wifi.sta.ssid), "%s", CONFIG_CHARGESENSE_WIFI_SSID);
    snprintf((char *)wifi.sta.password, sizeof(wifi.sta.password), "%s", CONFIG_CHARGESENSE_WIFI_PASSWORD);
    wifi.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi));
    ESP_ERROR_CHECK(esp_wifi_start());
    uint8_t id[16];
    esp_fill_random(id, sizeof(id));
    id[6] = (id[6] & 0x0f) | 0x40; id[8] = (id[8] & 0x3f) | 0x80;
    snprintf(boot_id, sizeof(boot_id),
        "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
        id[0],id[1],id[2],id[3],id[4],id[5],id[6],id[7],id[8],id[9],id[10],id[11],id[12],id[13],id[14],id[15]);
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, CONFIG_CHARGESENSE_NTP_SERVER);
    esp_sntp_init();
    queue = xQueueCreate(8, sizeof(message_t));
    configASSERT(queue);
    configASSERT(xTaskCreate(sender, "http_sender", 6144, NULL, 4, NULL) == pdPASS);
}

static void add_value(cJSON *object, const char *key, double value) {
    if (isfinite(value)) cJSON_AddNumberToObject(object, key, value);
    else cJSON_AddNullToObject(object, key);
}

void telemetry_submit(double voltage, double current, double power,
                      double temperature, const char *quality, bool simulated) {
    if (!queue) return;
    cJSON *root = cJSON_CreateObject();
    if (!root) return;
    cJSON_AddNumberToObject(root, "schemaVersion", 1);
    cJSON_AddStringToObject(root, "stationId", CONFIG_CHARGESENSE_STATION_ID);
    cJSON_AddStringToObject(root, "bootId", boot_id);
    cJSON_AddNumberToObject(root, "sequence", sequence++);
    cJSON_AddStringToObject(root, "source", simulated ? "simulated" : "sensor");
    cJSON_AddNumberToObject(root, "uptimeMs", esp_timer_get_time() / 1000);
    time_t now = time(NULL);
    if (now > 1704067200) {
        struct tm utc; char timestamp[32];
        gmtime_r(&now, &utc);
        strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", &utc);
        cJSON_AddStringToObject(root, "measuredAt", timestamp);
    } else cJSON_AddNullToObject(root, "measuredAt");
    cJSON_AddStringToObject(root, "quality", quality);
    cJSON *values = cJSON_AddObjectToObject(root, "measurements");
    if (!values) { cJSON_Delete(root); return; }
    add_value(values, "voltageV", voltage); add_value(values, "currentA", current);
    add_value(values, "activePowerW", power); add_value(values, "panelTempC", temperature);
    char *serialized = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!serialized) return;
    message_t msg;
    if (strlen(serialized) < sizeof(msg.json)) {
        strcpy(msg.json, serialized);
        if (xQueueSend(queue, &msg, 0) != pdTRUE) ESP_LOGW(TAG, "Fila cheia: nova leitura descartada");
    } else ESP_LOGE(TAG, "Mensagem excede buffer");
    cJSON_free(serialized);
}
#else
void telemetry_init(void) {}
void telemetry_submit(double v, double i, double p, double t, const char *q, bool s) {
    (void)v; (void)i; (void)p; (void)t; (void)q; (void)s;
}
#endif
