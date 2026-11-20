idf_component_register(SRCS "main.c" "measurement.c" "telemetry.c" INCLUDE_DIRS "."
    REQUIRES esp_adc esp_wifi esp_event esp_netif nvs_flash esp_http_client esp_timer json mbedtls lwip)

