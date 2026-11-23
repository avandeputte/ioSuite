#pragma once
#include <stdio.h>
extern int sim_quiet;
#define ESP_LOGE(tag, fmt, ...) fprintf(stderr, "E %s: " fmt "\n", tag, ##__VA_ARGS__)
#define ESP_LOGW(tag, fmt, ...) do { if (!sim_quiet) fprintf(stderr, "W %s: " fmt "\n", tag, ##__VA_ARGS__); } while (0)
#define ESP_LOGI(tag, fmt, ...) do { if (!sim_quiet) fprintf(stderr, "I %s: " fmt "\n", tag, ##__VA_ARGS__); } while (0)
#define ESP_LOGD(tag, fmt, ...) do {} while (0)
