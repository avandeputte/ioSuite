#pragma once
#include "FreeRTOS.h"
QueueHandle_t xQueueCreate(int n, int size);
BaseType_t xQueueSend(QueueHandle_t q, const void *item, TickType_t t);
BaseType_t xQueueReceive(QueueHandle_t q, void *item, TickType_t t);
