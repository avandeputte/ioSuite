#pragma once
#include "FreeRTOS.h"
void vTaskDelay(TickType_t t);
static inline BaseType_t xTaskCreatePinnedToCore(void (*fn)(void *), const char *n, int st, void *a, int pr, TaskHandle_t *h, int core) { if (h) *h = (void *)1; return 1; }
static inline BaseType_t xTaskCreate(void (*fn)(void *), const char *n, int st, void *a, int pr, TaskHandle_t *h) { if (h) *h = (void *)1; return 1; }
static inline void xTaskNotifyGive(TaskHandle_t h) { extern int sim_notified; sim_notified++; }
static inline uint32_t ulTaskNotifyTake(int c, TickType_t t) { return 0; }
