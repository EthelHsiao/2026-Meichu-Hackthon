#pragma once
// 複製這個檔案成 cam_wifi_local.h，填入你們共用熱點的帳密
// （cam_wifi_local.h 不會進 git，跟主板 telemetry_local.h 做法一致）。
//
// 這個熱點要跟主板 esp32-bringup 的 telemetry_local.h 填「同一個」SSID/密碼，
// 兩塊 ESP32 加上你的電腦都連同一個熱點，才會在同一個區網互相看得到。
//
// 重要：ESP32 系列都不支援 5GHz Wi-Fi，只能連 2.4GHz。很多手機熱點預設
// 開雙頻或 5GHz，記得確認手機熱點設定裡切成 2.4GHz（或雙頻同名）。
#define CAM_WIFI_SSID "your-hotspot"
#define CAM_WIFI_PASSWORD "your-password"
