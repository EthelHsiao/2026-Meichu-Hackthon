#pragma once
// ESP32-CAM 常見型號：AI-Thinker。下面是這個型號的標準固定腳位
// （相機排線本身已經決定這些接點，不是你可以自由選的接線）。
// 若你手上板子的絲印跟這裡兜不起來，很可能是別的廠牌（M5Camera /
// TTGO / WROVER-KIT 等），先拍照回報再確認。
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
