#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef void *TaskHandle_t;
typedef void *QueueHandle_t;
typedef void *SemaphoreHandle_t;
typedef int BaseType_t;
typedef uint32_t TickType_t;
#define pdTRUE 1
#define pdFALSE 0
#define pdPASS 1
#define portMAX_DELAY 0xffffffffu
#define pdMS_TO_TICKS(ms) (ms)
