// ============================================================
//  ESP32-CAM（AI-Thinker，OV2640）— 相機 + WiFi STA 串流測試
//
//  這塊板子只做一件事：拍照 + 用 WiFi 把畫面傳出去。
//  不接 FSR / IMU / LCD / 蜂鳴器 / 麥克風——那些都在主板 esp32-bringup。
//
//  網路模式：STA（加入既有熱點），不是自己開 AP。
//  原因：主板已經在用自己的 SoftAP 給電腦連，如果這塊板子也自己開一個
//  SoftAP，電腦的 Wi-Fi 網卡沒辦法同時連兩個 Wi-Fi 網路——這是實體限制，
//  不是效能問題。解法是主板改成 STA、這塊板子也是 STA，兩塊板子跟電腦
//  都加入「同一個」外部熱點（手機熱點或路由器都可以），彼此才能互通。
//  細節見 esp32-cam-bringup/docs/wiring_and_network.md。
// ============================================================
#include <Arduino.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include "esp_camera.h"
#include "camera_pins.h"
#include "cam_wifi_config.h"

static WiFiServer server(80);
static bool s_camReady = false;

static const char *STREAM_CONTENT_TYPE = "multipart/x-mixed-replace; boundary=frame";
static const char *STREAM_BOUNDARY = "\r\n--frame\r\n";

static bool initCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // 先求能動、能看到畫面，畫質/幀率之後再依實測調整——
  // 跟 FSR 分壓電阻先用 10kΩ 再依實測曲線調的做法一致。
  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;   // 640x480
    config.jpeg_quality = 12;            // 數字越小畫質越好、檔案越大
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_QVGA;  // 320x240，沒有 PSRAM 保守一點
    config.jpeg_quality = 15;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("esp_camera_init failed: 0x%x\n", err);
    return false;
  }
  return true;
}

static void skipRequestHeaders(WiFiClient &client) {
  while (client.connected() && client.available()) {
    String line = client.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) break;   // 空行 = headers 結束
  }
}

static void handleStream(WiFiClient &client) {
  client.println("HTTP/1.1 200 OK");
  client.print("Content-Type: ");
  client.println(STREAM_CONTENT_TYPE);
  client.println("Connection: close");
  client.println();

  uint32_t frames = 0;
  uint32_t lastFpsPrint = millis();
  while (client.connected()) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("frame capture failed");
      break;
    }
    client.print(STREAM_BOUNDARY);
    client.printf("Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len);
    client.write(fb->buf, fb->len);
    esp_camera_fb_return(fb);

    frames++;
    const uint32_t now = millis();
    if (now - lastFpsPrint >= 2000) {
      Serial.printf("streaming ~%.1f fps\n", frames * 1000.0 / (now - lastFpsPrint));
      frames = 0;
      lastFpsPrint = now;
    }
  }
}

static void handleSnapshot(WiFiClient &client) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    client.println("HTTP/1.1 500 Internal Server Error");
    client.println("Connection: close");
    client.println();
    return;
  }
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: image/jpeg");
  client.printf("Content-Length: %u\r\n", fb->len);
  client.println("Connection: close");
  client.println();
  client.write(fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

static void handleHealth(WiFiClient &client) {
  char body[192];
  snprintf(body, sizeof(body),
    "{\"schema_version\":1,\"ok\":true,\"device_id\":\"esp32cam-%012llx\",\"cam_ok\":%s}",
    (unsigned long long)ESP.getEfuseMac(), s_camReady ? "true" : "false");
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: application/json");
  client.println("Connection: close");
  client.println();
  client.print(body);
}

static void handleRoot(WiFiClient &client) {
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: text/html; charset=utf-8");
  client.println("Connection: close");
  client.println();
  client.println("<html><body style=\"background:#111;color:#eee;font-family:sans-serif\">"
                  "<h3>ESP32-CAM \xe6\xb8\xac\xe8\xa9\xa6</h3>"
                  "<img src=\"/api/v1/cam/stream\" style=\"max-width:100%\"/>"
                  "<p><a href=\"/api/v1/cam/snapshot\" style=\"color:#8cf\">snapshot</a> | "
                  "<a href=\"/api/v1/health\" style=\"color:#8cf\">health</a></p>"
                  "</body></html>");
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1000);
  Serial.println("\n=== ESP32-CAM: 相機 + WiFi STA 串流測試 ===");

  s_camReady = initCamera();
  Serial.printf("Camera init: %s\n", s_camReady ? "OK" : "FAILED（檢查排線方向與供電）");

  WiFi.mode(WIFI_STA);
  WiFi.begin(CAM_WIFI_SSID, CAM_WIFI_PASSWORD);
  Serial.printf("Joining WiFi \"%s\"", CAM_WIFI_SSID);
  uint32_t startMs = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
    if (millis() - startMs > 20000) {
      Serial.println("\n20 秒還沒連上，檢查 SSID/密碼是否正確、熱點是否為 2.4GHz。");
      startMs = millis();
    }
  }
  Serial.println();
  Serial.printf("Connected. IP = %s\n", WiFi.localIP().toString().c_str());
  Serial.println("在跟這台 ESP32-CAM 同一個熱點下的裝置，瀏覽器打開下面網址：");
  Serial.printf("  http://%s/\n", WiFi.localIP().toString().c_str());

  // mDNS：熱點模式下這塊板子的 IP 是動態的（DHCP 給的，每次不一定
  // 一樣），加 mDNS 之後同一個熱點下的裝置可以固定用 esp32-cam.local
  // 連過來，不用每次開機都去查/改 IP。手機熱點跟大部分路由器都支援
  // mDNS，但如果 AIPC 那台電腦連不到 .local 網址，通常是還沒裝
  // avahi-daemon（Ubuntu：sudo apt install avahi-daemon libnss-mdns），
  // 這種情況下退回用上面印出的實際 IP 一樣可以連。
  if (MDNS.begin("esp32-cam")) {
    MDNS.addService("http", "tcp", 80);
    Serial.println("mDNS 就緒：http://esp32-cam.local/");
  } else {
    Serial.println("mDNS 啟動失敗（不影響用 IP 直接連）");
  }

  server.begin();
}

void loop() {
  WiFiClient client = server.available();
  if (!client) {
    delay(5);
    return;
  }

  String reqLine = client.readStringUntil('\r');
  client.readStringUntil('\n');
  skipRequestHeaders(client);

  if (reqLine.indexOf("GET /api/v1/cam/stream") >= 0) {
    handleStream(client);
  } else if (reqLine.indexOf("GET /api/v1/cam/snapshot") >= 0) {
    handleSnapshot(client);
  } else if (reqLine.indexOf("GET /api/v1/health") >= 0) {
    handleHealth(client);
  } else {
    handleRoot(client);
  }
  delay(1);
  client.stop();
}
