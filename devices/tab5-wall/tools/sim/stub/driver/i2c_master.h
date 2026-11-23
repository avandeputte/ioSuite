#pragma once
#include <stdint.h>
typedef void *i2c_master_dev_handle_t;
typedef void *i2c_master_bus_handle_t;
typedef struct { int dev_addr_length, device_address, scl_speed_hz; } i2c_device_config_t;
#define I2C_ADDR_BIT_LEN_7 0
#define ESP_OK 0
static inline int i2c_master_transmit_receive(void *d, const uint8_t *w, int wn, uint8_t *r, int rn, int t) { return -1; }
static inline int i2c_master_probe(void *b, int a, int t) { return -1; }
static inline int i2c_master_bus_add_device(void *b, const i2c_device_config_t *c, i2c_master_dev_handle_t *d) { return -1; }
static inline int i2c_master_transmit(void *d, const uint8_t *w, int n, int t) { return -1; }
