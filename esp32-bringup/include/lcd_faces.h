#pragma once
// ============================================================
//  lcd_faces.h — 黑貓臉：一直在動的大圓眼 + 一行一行出現的中文台詞
//  Stage 5（s5_lcd，只有螢幕）跟 Stage 13（s13_companion，整合 build）共用這一份，
//  兩邊畫出來的臉完全一樣，不會再有「改了一邊忘了另一邊」的問題。
//
//  畫面（橫放 160x128）：
//    ┌──────────────────┐
//    |    (●)    (●)    |  ← 淡藍圓眼 + 黑瞳孔：會四處看、會眨眼、隨情緒變形
//    |        w         |  ← 小嘴巴，說話時一開一合（idle / dizzy 沒有嘴巴）
//    |   嗨，我在這裡   |  ← 台詞只有一行：逐字出現，這行講完停一下就消失，換下一行
//    └──────────────────┘
//
//  眼睛不是「換一張圖」：每個情緒只是一組目標參數（眼睛大小、瞳孔大小、
//  上眼皮位置與斜度），每一幀都往目標值平滑靠近，換情緒是連續變形過去的；
//  再疊上隨機視線、呼吸、眨眼，眼睛就一直是活的。dizzy 的螺旋眼跟圓眼差太多，
//  切換時會先眨一下眼，在閉眼那一瞬間換掉。
//
//  整個畫面先畫在記憶體畫布（GFXcanvas16）再一次推到螢幕，不會閃爍。
//  台詞用 font_tc12.h（繁中 12px，常用 5401 字 + 標點 + ASCII），罕用字顯示成空白。
//
//  對外介面（呼叫端：companion_app.h 的下行指令、main.cpp 的 Stage 5）：
//    lcdInit()                        開機初始化，要在 SPI/WiFi 之後
//    lcdSetMoodByName("thinking")     換情緒
//    lcdSay(text, done, exprOrNull)   排一句台詞；done=false 代表這句還沒講完（串流）
//    lcdClearText()                   清掉台詞和還沒講的句子
//    lcdUpdate(millis())              放在 loop() 裡，負責動畫與逐字顯示
// ============================================================
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <U8g2_for_Adafruit_GFX.h>
#include "board_config.h"
#include "font_tc12.h"   // 繁中 12px，由 tools/make_font_tc12.py 產生

static Adafruit_ST7735 lcdTft(PIN_LCD_CS, PIN_LCD_DC, PIN_LCD_RST);
static U8G2_FOR_ADAFRUIT_GFX lcdU8g2;   // 台詞用：Adafruit 內建字型只有 ASCII，中文會變亂碼

// 1 = 橫放；畫面上下顛倒就改成 3
static const uint8_t LCD_ROTATION = 1;
// 畫面有雜點就降到 16000000
static const uint32_t LCD_SPI_HZ = 27000000;
// 每幀時間。s13_companion 還要餵麥克風 I2S 跟 20Hz telemetry，所以那邊調慢一點，
// 把 SPI 跟 CPU 留給音訊（見 companion_app.h 的 #define）。
#ifndef LCD_FRAME_MS
#define LCD_FRAME_MS 33
#endif

static const uint16_t LCD_COLOR_BG  = ST77XX_BLACK;
static const uint16_t LCD_COLOR_FG  = ST77XX_WHITE;   // 台詞
static const uint16_t LCD_COLOR_EYE = 0xBF3F;         // 淡藍 (191,230,255)，眼睛和嘴巴共用

// ---- 版面（以 160x128 橫放為準）----
static const int LCD_EYE_Y     = 44;    // 眼睛中心 y
static const int LCD_EYE_DX    = 37;    // 眼睛離中線距離
static const int LCD_MOUTH_Y   = 82;    // 嘴巴中心 y
static const int LCD_TEXT_TOP  = 98;    // 台詞區上緣：臉再怎麼動都不會畫到這條線以下
static const int LCD_TEXT_BASE = 117;   // 台詞 baseline

static int lcdW = 0, lcdH = 0, lcdCx = 0;
static GFXcanvas16 *lcdCanvas = nullptr;

// ============================================================
//  情緒：一組眼睛目標值 + 一種「視線習慣」
// ============================================================
enum LcdMood { LCD_NEUTRAL, LCD_IDLE, LCD_LOVE, LCD_SAD, LCD_SLEEPY, LCD_SURPRISED,
               LCD_THINKING, LCD_WORRIED, LCD_DIZZY, LCD_MOOD_COUNT };
static const char *LCD_MOOD_NAMES[LCD_MOOD_COUNT] = {"neutral", "idle", "love", "sad", "sleepy",
                                                     "surprised", "thinking", "worried", "dizzy"};

struct LcdMoodStyle {
  float eyeR;        // 眼睛半徑
  float pupilR;      // 瞳孔半徑：大 = 溫柔、小 = 驚訝/緊張
  float lidTop;      // 上眼皮蓋住多少 0~1
  float lidTilt;     // 上眼皮斜度：+ 外側低（難過/擔心）
  float squintR;     // 右眼額外多瞇多少（思考時一眼大一眼小）
  uint16_t lookMinMs, lookMaxMs;   // 多久換一次視線
  float lookX, lookY;              // 視線亂飄的範圍（-1~1）
  float biasX, biasY;              // 視線偏好的方向
  float gazeTau;                   // 眼球移動時間常數（ms），小 = 動得快
};

static const LcdMoodStyle LCD_MOOD_STYLE[LCD_MOOD_COUNT] = {
  // eyeR pupil lidT  tilt  sqR   minMs maxMs lookX lookY biasX  biasY  tau
  {  27,  20,  0.00, 0.0,  0.00,  900, 3000, 1.0,  0.6,  0.0,   0.0,   70 },  // neutral
  {  27,  20,  0.00, 0.0,  0.00, 1400, 3000, 1.0,  0.15, 0.0,   0.0,  110 },  // idle：左顧右盼（見 lcdUpdateGaze）
  {  28,  23,  0.00, 0.0,  0.00, 1600, 3600, 0.4,  0.25, 0.0,   0.0,  160 },  // love
  {  26,  21,  0.30, 0.8,  0.00, 1800, 3800, 0.5,  0.2,  0.0,   0.7,  140 },  // sad
  {  26,  20,  0.55, 0.0,  0.00, 2500, 5000, 0.4,  0.2,  0.0,   0.4,  280 },  // sleepy
  {  30,  14,  0.00, 0.0,  0.00, 1500, 3000, 0.15, 0.15, 0.0,   0.0,   45 },  // surprised
  {  27,  19,  0.10, 0.0,  0.18, 1300, 2600, 0.3,  0.3,  0.75, -0.75, 120 },  // thinking
  {  27,  17,  0.20, 0.6,  0.00,  350, 1000, 1.0,  0.4,  0.0,   0.1,   45 },  // worried
  {  27,  20,  0.00, 0.0,  0.00, 1000, 1000, 0.0,  0.0,  0.0,   0.0,   70 },  // dizzy：畫螺旋，不用這些值
};

// 舊的表情名稱：ai-pc-agent/protocol.py 與 MI300 目前還在用 happy/joy，
// 先當 neutral 顯示（w 嘴本來就是笑臉），等兩邊一起換掉表情清單再移除。
static int lcdMoodFromName(const char *name) {
  for (int i = 0; i < LCD_MOOD_COUNT; i++) {
    if (strcmp(name, LCD_MOOD_NAMES[i]) == 0) return i;
  }
  if (strcmp(name, "happy") == 0 || strcmp(name, "joy") == 0) return LCD_NEUTRAL;
  return -1;
}

// 眼睛現在的樣子（每幀往目標靠近）
struct LcdEyeState { float eyeR, pupilR, lidTop, lidTilt, squintR; };
static LcdEyeState lcdEye, lcdEyeTarget;
static LcdMood  lcdMood = LCD_NEUTRAL;
static bool     lcdShowSpiral = false;   // 畫面上現在是不是螺旋眼（眨眼中途才切換）
static float    lcdGazeX = 0, lcdGazeY = 0, lcdGazeTX = 0, lcdGazeTY = 0;   // -1~1
static float    lcdLookSide = 1;
static uint32_t lcdNextLookAt = 0;
static uint32_t lcdBlinkAt = 0, lcdNextBlinkAt = 0;
static bool     lcdDoubleBlink = false;
static bool     lcdTalking = false;      // 台詞正在逐字出現

static void lcdSetMood(LcdMood m) {
  lcdMood = m;
  const LcdMoodStyle &st = LCD_MOOD_STYLE[m];
  lcdEyeTarget = {st.eyeR, st.pupilR, st.lidTop, st.lidTilt, st.squintR};
  lcdNextLookAt = 0;   // 換情緒時馬上換個視線，看起來像有反應
}

// 認得的名字才換；不認得的保持原樣（不要因為打錯字就把臉變成預設表情）
static bool lcdSetMoodByName(const char *name) {
  const int m = lcdMoodFromName(name);
  if (m < 0) return false;
  lcdSetMood((LcdMood)m);
  return true;
}

static float lcdRand() { return (esp_random() & 0xFFFF) / 65535.0f; }
static int16_t lcdPx(float v) { return (int16_t)lroundf(v); }

// 指數平滑：不管幀率多少，都在 tau 毫秒左右走完約 63%
static float lcdApproach(float cur, float target, float dtMs, float tauMs) {
  return cur + (target - cur) * (1.0f - expf(-dtMs / tauMs));
}

// ---- 視線：隨機挑下一個要看的點，眼球平滑移過去 ----
static void lcdUpdateGaze(uint32_t now) {
  if (now < lcdNextLookAt) return;
  const LcdMoodStyle &st = LCD_MOOD_STYLE[lcdMood];
  lcdNextLookAt = now + st.lookMinMs + esp_random() % (st.lookMaxMs - st.lookMinMs + 1);

  if (lcdMood == LCD_IDLE) {   // 左顧右盼：左右輪流看
    lcdLookSide = -lcdLookSide;
    lcdGazeTX = lcdLookSide * (0.7f + 0.3f * lcdRand());
    lcdGazeTY = (lcdRand() * 2 - 1) * st.lookY;
    return;
  }
  if (lcdMood == LCD_THINKING && lcdRand() < 0.25f) lcdLookSide = -lcdLookSide;   // 左上、右上輪流看
  float bx = st.biasX * lcdLookSide, by = st.biasY;
  float rx = st.lookX, ry = st.lookY;
  if (lcdTalking) { bx = 0; by = 0; rx *= 0.3f; ry *= 0.3f; }   // 說話時看著使用者

  if (lcdRand() < 0.35f) {   // 常常回到偏好位置，才不會一直亂飄
    lcdGazeTX = bx;
    lcdGazeTY = by;
    return;
  }
  lcdGazeTX = constrain(bx + (lcdRand() * 2 - 1) * rx, -1.0f, 1.0f);
  lcdGazeTY = constrain(by + (lcdRand() * 2 - 1) * ry, -1.0f, 1.0f);
}

// ---- 眨眼：回傳 0（張開）~ 1（閉上）----
static float lcdBlinkAmount(uint32_t now) {
  const bool sleepy = lcdMood == LCD_SLEEPY;
  const uint32_t closeMs = sleepy ? 220 : 70, holdMs = sleepy ? 180 : 40, openMs = sleepy ? 320 : 100;
  if (lcdBlinkAt == 0) {
    // 畫面上的形狀（圓眼／螺旋）跟情緒對不上就馬上眨一下，在閉眼時換掉；螺旋眼平常不自己眨
    const bool needSwap = lcdShowSpiral != (lcdMood == LCD_DIZZY);
    if (!needSwap && (now < lcdNextBlinkAt || lcdShowSpiral)) return 0;
    lcdBlinkAt = now;
  }
  const uint32_t t = now - lcdBlinkAt;
  if (t < closeMs) return (float)t / closeMs;
  if (t < closeMs + holdMs) return 1;
  if (t < closeMs + holdMs + openMs) return 1 - (float)(t - closeMs - holdMs) / openMs;

  lcdBlinkAt = 0;   // 眨完了，排下一次；偶爾連眨兩下
  if (!lcdDoubleBlink && lcdRand() < 0.15f) {
    lcdDoubleBlink = true;
    lcdNextBlinkAt = now + 120;
  } else {
    lcdDoubleBlink = false;
    lcdNextBlinkAt = now + (lcdMood == LCD_SURPRISED ? 4000 : 2200) + esp_random() % 3500;
  }
  return 0;
}

// ---- 畫一隻眼睛：淡藍圓 → 黑瞳孔 → 上眼皮 ----
static void lcdDrawEye(GFXcanvas16 &c, float cx, float cy, bool isLeft, float blink, float breath) {
  const LcdEyeState &e = lcdEye;
  const float R  = e.eyeR + breath;
  const float ex = cx + lcdGazeX * 5, ey = cy + lcdGazeY * 4;   // 整顆眼睛也跟著視線偏一點
  c.fillCircle(lcdPx(ex), lcdPx(ey), lcdPx(R), LCD_COLOR_EYE);

  const float maxOff = max(0.0f, R - e.pupilR - 4);   // 瞳孔不能跑出淡藍圓
  c.fillCircle(lcdPx(ex + lcdGazeX * maxOff), lcdPx(ey + lcdGazeY * maxOff), lcdPx(e.pupilR), LCD_COLOR_BG);

  // 上眼皮：黑色多邊形從上面蓋下來，可以歪
  float lid = e.lidTop + (isLeft ? 0 : e.squintR);
  lid = min(1.0f, lid + (1 - lid) * blink);   // 眨眼 = 眼皮蓋到底
  const float top  = ey - R - 3;
  const float lidY = ey - R + 2 * R * lid;
  const float tilt = e.lidTilt * R * 0.55f * (1 - blink);   // 閉眼時拉平
  const float x0 = ex - R - 3, x1 = ex + R + 3;
  const float yL = lidY + (isLeft ? tilt : -tilt);           // 左眼的外側在左邊
  const float yR = lidY + (isLeft ? -tilt : tilt);
  if (max(yL, yR) > top) {
    c.fillTriangle(lcdPx(x0), lcdPx(top), lcdPx(x1), lcdPx(top), lcdPx(x0), lcdPx(yL), LCD_COLOR_BG);
    c.fillTriangle(lcdPx(x1), lcdPx(top), lcdPx(x1), lcdPx(yR), lcdPx(x0), lcdPx(yL), LCD_COLOR_BG);
  }
}

// ---- dizzy 的螺旋眼：沿著螺旋線蓋一串小圓點，就是一條粗線 ----
static void lcdDrawSpiral(GFXcanvas16 &c, float cx, float cy, float rot, float dir, float scale) {
  for (int i = 0; i <= 220; i++) {
    const float t = i / 220.0f;
    const float a = dir * t * 5 * PI + rot;
    const float r = (2 + t * 23) * scale;
    c.fillCircle(lcdPx(cx + cosf(a) * r), lcdPx(cy + sinf(a) * r), 2, LCD_COLOR_EYE);
  }
}

// ---- 嘴巴：平常是小 w，說話時一開一合 ----
static void lcdDrawMouth(GFXcanvas16 &c, int x, int y, uint32_t now) {
  if (lcdTalking && (now / 130) % 2 == 0) {
    c.fillRoundRect(x - 3, y - 3, 7, 8, 3, LCD_COLOR_EYE);
    return;
  }
  for (int r = 3; r <= 4; r++) {   // 疊兩圈 = 2px 粗；drawCircleHelper 4|8 = 下半圓
    c.drawCircleHelper(x - 4, y - 1, r, 4 | 8, LCD_COLOR_EYE);
    c.drawCircleHelper(x + 4, y - 1, r, 4 | 8, LCD_COLOR_EYE);
  }
}

// ============================================================
//  台詞：只有一行。逐字出現，這行寫滿或這句講完就停一下，然後整行消失換下一行
//  串流時同一句會陸續補字（done=false），補到 done=true 才算講完
// ============================================================
static const int      LCD_TEXT_MAX_W      = 148;    // 一行最寬（左右各留 6px）
static const int      LCD_TEXT_HANG_W     = 156;    // 行尾標點可以稍微凸出去，不要自己跑到下一行開頭
static const uint32_t LCD_CHAR_MS         = 85;     // 打字速度（中文）
static const uint32_t LCD_CHAR_MS_ASCII   = 55;     // 打字速度（英文、數字）
static const uint32_t LCD_LINE_HOLD_MS    = 900;    // 一行寫滿，停多久再換下一行
static const uint32_t LCD_SENTENCE_HOLD_MS = 1500;  // 一句講完，停多久才換下一句
static const uint32_t LCD_TEXT_LINGER_MS  = 8000;   // 講完後沒有下一句，最後一行留多久才消失
static const uint32_t LCD_STREAM_TIMEOUT_MS = 5000; // 串流中的句子多久沒收到新字，就當它講完
static const int      LCD_SENTENCE_MAX_BYTES = 600; // 一句最多收多少 byte（約 200 個中文字）

struct LcdSentence { String text; bool done; int8_t mood; };   // mood = -1：不換情緒
static const int LCD_QUEUE_MAX = 6;
static LcdSentence lcdQueue[LCD_QUEUE_MAX];
static int lcdQHead = 0, lcdQLen = 0;

static LcdSentence lcdCur;
static bool     lcdCurActive = false;
static int      lcdPos = 0;               // 已經顯示到第幾個 byte
static String   lcdLine;                  // 畫面上那一行
static bool     lcdLineDone = false;      // 這一行講完了，停一下就換
static bool     lcdSentenceEnded = false; // 這句最後一行已經開始停頓
static uint32_t lcdNextCharAt = 0, lcdLingerUntil = 0, lcdLastChunkAt = 0;

static int lcdUtf8Len(uint8_t lead) {
  if (lead < 0x80) return 1;
  if ((lead >> 5) == 0x6) return 2;
  if ((lead >> 4) == 0xE) return 3;
  if ((lead >> 3) == 0x1E) return 4;
  return 1;
}

static bool lcdIsClosingPunct(const String &ch) {
  static const char *const PUNCT[] = {"，", "。", "！", "？", "、", "…", "；", "：", "」", "』", "）", "～",
                                      ",", ".", "!", "?", ";", ":", ")"};
  for (const char *p : PUNCT) {
    if (ch == p) return true;
  }
  return false;
}

// 從 i 開始的英文單字（判斷整個單字放不放得下）
static String lcdAsciiWordAt(const String &s, int i) {
  int j = i;
  while (j < (int)s.length() && (uint8_t)s[j] < 0x80 && s[j] != ' ' && s[j] != '\n') j++;
  return s.substring(i, j);
}

static int lcdTextWidth(const String &s) { return lcdU8g2.getUTF8Width(s.c_str()); }

static void lcdAppendCapped(String &dst, const String &text) {
  if ((int)(dst.length() + text.length()) <= LCD_SENTENCE_MAX_BYTES) {
    dst += text;
    return;
  }
  int keep = LCD_SENTENCE_MAX_BYTES - dst.length();
  while (keep > 0 && ((uint8_t)text[keep] & 0xC0) == 0x80) keep--;   // 不要切在中文字中間
  if (keep > 0) dst += text.substring(0, keep);
  Serial.println(F("台詞太長，後面的丟掉"));
}

// 排一句台詞。done=false 代表這句還沒講完（串流，後面還會補字）；
// exprName 可以是 nullptr（不換情緒）。
static void lcdSay(const String &text, bool done = true, const char *exprName = nullptr) {
  lcdLastChunkAt = millis();
  const int mood = exprName != nullptr ? lcdMoodFromName(exprName) : -1;

  // 串流：最後一句還沒講完，就接在它後面
  LcdSentence *open = nullptr;
  if (lcdQLen > 0) {
    LcdSentence &last = lcdQueue[(lcdQHead + lcdQLen - 1) % LCD_QUEUE_MAX];
    if (!last.done) open = &last;
  } else if (lcdCurActive && !lcdCur.done) {
    open = &lcdCur;
  }
  // 串流只有第一段帶 expr；還開著的句子又收到帶 expr 的訊息，代表上一句的 done 掉了、這是新的一句
  if (open && mood >= 0) {
    open->done = true;
    open = nullptr;
  }
  if (open) {
    lcdAppendCapped(open->text, text);
    open->done = done;
    return;
  }
  if (lcdQLen == LCD_QUEUE_MAX) {
    Serial.println(F("台詞佇列滿了，丟掉最舊的一句"));
    lcdQHead = (lcdQHead + 1) % LCD_QUEUE_MAX;
    lcdQLen--;
  }
  LcdSentence &slot = lcdQueue[(lcdQHead + lcdQLen) % LCD_QUEUE_MAX];
  slot = {"", done, (int8_t)mood};
  lcdAppendCapped(slot.text, text);
  lcdQLen++;
}

static void lcdClearText() {
  for (int i = 0; i < LCD_QUEUE_MAX; i++) lcdQueue[i] = LcdSentence();
  lcdQHead = lcdQLen = 0;
  lcdCur = LcdSentence();
  lcdCurActive = false;
  lcdPos = 0;
  lcdLine = "";
  lcdLineDone = false;
}

// 這一行講完：停一下，下次要出字時整行消失
static void lcdEndLine(uint32_t now, uint32_t holdMs) {
  lcdLineDone = true;
  lcdNextCharAt = now + holdMs;
}

// 顯示下一個字
static void lcdRevealNext(uint32_t now) {
  const String &s = lcdCur.text;
  if (lcdLineDone) {   // 上一行停夠了，消失
    lcdLine = "";
    lcdLineDone = false;
  }

  const uint8_t lead = s[lcdPos];
  const int n = lcdUtf8Len(lead);
  if (lcdPos + n > (int)s.length()) {   // 中文字的 byte 還沒收齊（串流切在字中間）
    if (lcdCur.done) lcdPos = s.length();
    return;
  }
  const String ch = s.substring(lcdPos, lcdPos + n);

  if (lead == '\n') {
    lcdPos += n;
    if (lcdLine.length() > 0) lcdEndLine(now, LCD_LINE_HOLD_MS);
    return;
  }
  if (lead == ' ' && lcdLine.length() == 0) {   // 行首空白不顯示
    lcdPos += n;
    return;
  }

  // 放不下就先把這行結束；英文看整個單字，行尾標點可以稍微凸出去
  const bool wordStart = lead < 0x80 && lead != ' ' &&
                         (lcdPos == 0 || s[lcdPos - 1] == ' ' || (uint8_t)s[lcdPos - 1] >= 0x80);   // 空白或中文後面都算新單字
  const String next = wordStart ? lcdAsciiWordAt(s, lcdPos) : ch;
  const int limit = lcdIsClosingPunct(ch) ? LCD_TEXT_HANG_W : LCD_TEXT_MAX_W;
  if (lcdLine.length() > 0 && lcdTextWidth(lcdLine + next) > limit) {
    lcdEndLine(now, LCD_LINE_HOLD_MS);
    return;
  }

  lcdPos += n;
  lcdLine += ch;
  const bool stop  = ch == "。" || ch == "！" || ch == "？" || ch == "…" || lead == '.' || lead == '!' || lead == '?';
  const bool pause = ch == "，" || ch == "、" || lead == ',';
  lcdNextCharAt = now + (stop ? 260 : pause ? 140 : lead < 0x80 ? LCD_CHAR_MS_ASCII : LCD_CHAR_MS);
}

static void lcdUpdateSpeech(uint32_t now) {
  if (!lcdCurActive) {
    if (lcdQLen == 0) {
      if (lcdLine.length() > 0 && now >= lcdLingerUntil) lcdLine = "";   // 講完很久了，讓最後一行消失
      return;
    }
    lcdCur = lcdQueue[lcdQHead];
    lcdQueue[lcdQHead] = LcdSentence();
    lcdQHead = (lcdQHead + 1) % LCD_QUEUE_MAX;
    lcdQLen--;
    lcdCurActive = true;
    lcdPos = 0;
    lcdLine = "";
    lcdLineDone = false;
    lcdSentenceEnded = false;
    lcdNextCharAt = now;
    if (lcdCur.mood >= 0) lcdSetMood((LcdMood)lcdCur.mood);
  }

  if (now < lcdNextCharAt) return;
  if (lcdPos < (int)lcdCur.text.length()) {
    lcdRevealNext(now);
    return;
  }
  if (!lcdCur.done) {         // 串流還沒講完，等下一段；太久沒收到就當它講完
    if (now - lcdLastChunkAt < LCD_STREAM_TIMEOUT_MS) return;
    Serial.println(F("串流太久沒收到新字，這句當作講完"));
    lcdCur.done = true;
  }
  if (!lcdSentenceEnded) {    // 這句剛講完：最後一行停久一點
    lcdSentenceEnded = true;
    lcdEndLine(now, LCD_SENTENCE_HOLD_MS);
    return;
  }
  lcdCurActive = false;       // 停夠了：有下一句就換（換的時候這行才消失），沒有就留著一陣子
  lcdLingerUntil = now + LCD_TEXT_LINGER_MS;
}

// ---- 一幀：更新參數 → 臉 → 台詞 → 一次推上螢幕 ----
static void lcdRenderFrame(uint32_t now) {
  static uint32_t lastFrame = 0;
  if (now - lastFrame < LCD_FRAME_MS) return;
  const float dt = min<uint32_t>(now - lastFrame, 100);
  lastFrame = now;

  const float tau = 110;   // 換情緒時眼睛變形的速度
  lcdEye.eyeR    = lcdApproach(lcdEye.eyeR,    lcdEyeTarget.eyeR,    dt, tau);
  lcdEye.pupilR  = lcdApproach(lcdEye.pupilR,  lcdEyeTarget.pupilR,  dt, tau);
  lcdEye.lidTop  = lcdApproach(lcdEye.lidTop,  lcdEyeTarget.lidTop,  dt, tau);
  lcdEye.lidTilt = lcdApproach(lcdEye.lidTilt, lcdEyeTarget.lidTilt, dt, tau);
  lcdEye.squintR = lcdApproach(lcdEye.squintR, lcdEyeTarget.squintR, dt, tau);

  lcdUpdateGaze(now);
  const float gazeTau = LCD_MOOD_STYLE[lcdMood].gazeTau;
  lcdGazeX = lcdApproach(lcdGazeX, lcdGazeTX, dt, gazeTau);
  lcdGazeY = lcdApproach(lcdGazeY, lcdGazeTY, dt, gazeTau);

  // 呼吸：整張臉慢慢上下浮動、眼睛微微縮放；love 輕輕左右晃、dizzy 晃比較大
  const float phase  = now * (TWO_PI / 3200.0f);
  const float breath = sinf(phase) * 0.7f;
  const float bob    = sinf(phase) * 1.4f;
  float sway = 0;
  if (lcdMood == LCD_LOVE)  sway = sinf(now * (TWO_PI / 2400.0f)) * 3;
  if (lcdMood == LCD_DIZZY) sway = sinf(now * (TWO_PI / 1600.0f)) * 4;

  const float blink = lcdBlinkAmount(now);
  if (blink > 0.95f) lcdShowSpiral = lcdMood == LCD_DIZZY;   // 閉眼那一瞬間換形狀

  GFXcanvas16 &c = *lcdCanvas;
  c.fillScreen(LCD_COLOR_BG);
  const float lx = lcdCx - LCD_EYE_DX + sway, rx = lcdCx + LCD_EYE_DX + sway, ey = LCD_EYE_Y + bob;
  if (lcdShowSpiral) {
    const float rot = now / 260.0f;
    lcdDrawSpiral(c, lx, ey, rot, 1, 1 - blink);
    lcdDrawSpiral(c, rx, ey, -rot, -1, 1 - blink);
  } else {
    lcdDrawEye(c, lx, ey, true, blink, breath);
    lcdDrawEye(c, rx, ey, false, blink, breath);
  }
  if (lcdMood != LCD_IDLE && lcdMood != LCD_DIZZY) {
    lcdDrawMouth(c, lcdPx(lcdCx + sway + lcdGazeX * 2), lcdPx(LCD_MOUTH_Y + bob), now);
  }

  // 台詞區先整條塗黑，臉怎麼動都不會蓋到字
  c.fillRect(0, LCD_TEXT_TOP, lcdW, lcdH - LCD_TEXT_TOP, LCD_COLOR_BG);
  if (lcdLine.length() > 0) {
    lcdU8g2.drawUTF8((lcdW - lcdTextWidth(lcdLine)) / 2, LCD_TEXT_BASE, lcdLine.c_str());
  }
  lcdTft.drawRGBBitmap(0, 0, c.getBuffer(), c.width(), c.height());
}

// 放在 loop() 裡：逐字顯示 + 動畫
static void lcdUpdate(uint32_t now) {
  if (lcdCanvas == nullptr || lcdCanvas->getBuffer() == nullptr) return;   // 畫布配置失敗，臉停用
  lcdUpdateSpeech(now);
  lcdTalking = lcdCurActive && lcdPos < (int)lcdCur.text.length() && !lcdLineDone;
  lcdRenderFrame(now);
}

static void lcdInit() {
  lcdTft.initR(INITR_BLACKTAB);   // 顏色不對或邊緣有雜線：改 INITR_GREENTAB / INITR_REDTAB
  lcdTft.setSPISpeed(LCD_SPI_HZ);
  lcdTft.setRotation(LCD_ROTATION);
  lcdW  = lcdTft.width();
  lcdH  = lcdTft.height();
  lcdCx = lcdW / 2;
  lcdTft.fillScreen(LCD_COLOR_BG);

  lcdCanvas = new GFXcanvas16(lcdW, lcdH);
  if (lcdCanvas->getBuffer() == nullptr) {   // 記憶體不夠：顯示錯誤就好，不要讓後面畫到空指標
    Serial.println(F("!! 畫布記憶體配置失敗，臉部停用"));
    lcdTft.setTextColor(ST77XX_RED);
    lcdTft.setCursor(4, 60);
    lcdTft.print("canvas alloc failed");
    return;
  }

  lcdU8g2.begin(*lcdCanvas);
  lcdU8g2.setFont(u8g2_font_tc12);
  lcdU8g2.setFontMode(1);   // 透明背景
  lcdU8g2.setForegroundColor(LCD_COLOR_FG);

  lcdSetMood(LCD_NEUTRAL);
  lcdEye = lcdEyeTarget;
  lcdNextBlinkAt = millis() + 1500;
}
