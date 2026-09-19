#pragma once
// ============================================================
//  mic_stream.h — INMP441 I2S 麥克風讀取，從 src/main.cpp 的 Stage 11/12
//  搬出來給 Stage 13（s13_companion）重用。
//
//  沿用 Stage 11/12 已經實機驗證過的立體聲繞道（classic ESP32 的 I2S RX
//  設成 ONLY_LEFT/ONLY_RIGHT 單聲道模式讀回來全部是 0 的已知限制，改用
//  I2S_CHANNEL_FMT_RIGHT_LEFT 立體聲、只取聲道 0）跟聲道 0 取樣的做法，
//  差別只是輸出目標從 Serial 921600 baud 換成呼叫端決定（Stage 13 接到
//  WebSocket binary frame）。
//
//  跟 Stage 11/12 的關鍵差異：i2s_read() 這裡用 ticks_to_wait=0（不等待），
//  因為 Stage 13 的 loop() 同時還要處理 WS/HTTP/FSR 取樣，不能被麥克風
//  卡住；讀不到資料就回 0，呼叫端（companion_app.h）的 loop() 那一輪
//  什麼都不送，下一輪再試。這個非阻塞行為沒有實機驗證過會不會漏太多
//  音框、聲音聽起來夠不夠連續，需要實機測試回報。
// ============================================================
#include <driver/i2s.h>
#include "board_config.h"

static const int MIC_CHUNK_FRAMES = 256;  // 跟 Stage 11/12 一致
static int32_t s_micRaw[MIC_CHUNK_FRAMES * 2];
static int16_t s_micPcm[MIC_CHUNK_FRAMES];
static bool s_micReady = false;

static bool micInit() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = MIC_SAMPLE_RATE_HZ;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 4;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;

  i2s_pin_config_t pins = {};
  pins.bck_io_num = PIN_MIC_SCK;
  pins.ws_io_num = PIN_MIC_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = PIN_MIC_SD;

  if (i2s_driver_install(MIC_I2S_PORT, &cfg, 0, nullptr) != ESP_OK) return false;
  if (i2s_set_pin(MIC_I2S_PORT, &pins) != ESP_OK) return false;
  s_micReady = true;
  return true;
}

// 非阻塞讀一個 chunk，回傳實際讀到的 byte 數（0 = 這輪沒有新資料或還沒 init）。
// s_micPcm 是單聲道 int16、16kHz，呼叫端讀到非 0 就可以直接把
// s_micPcm/回傳值 送出去（例如 WebSocket binary frame）。
static size_t micReadChunk() {
  if (!s_micReady) return 0;
  size_t bytesRead = 0;
  const esp_err_t err = i2s_read(MIC_I2S_PORT, (void *)s_micRaw, sizeof(s_micRaw), &bytesRead, 0);
  if (err != ESP_OK || bytesRead == 0) return 0;

  const int frames = bytesRead / sizeof(int32_t) / 2;
  for (int i = 0; i < frames; i++) {
    // 只取聲道 0（Stage 11 實測確認是有資料的那個），跟 Stage 12 一致的量級換算，
    // 含溢位保護（clamp）避免大聲時數值繞回負數變成爆音雜訊。
    int32_t v = s_micRaw[i * 2] >> 13;
    if (v > 32767) v = 32767;
    if (v < -32768) v = -32768;
    s_micPcm[i] = (int16_t)v;
  }
  return frames * sizeof(int16_t);
}
