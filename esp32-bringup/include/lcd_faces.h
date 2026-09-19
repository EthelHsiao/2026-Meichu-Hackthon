#pragma once
// ============================================================
//  lcd_faces.h — LCD 表情 + 文字繪製，從 src/main.cpp 的 Stage 5（s5_lcd）搬出來
//  獨立成 header，供 Stage 13（s13_companion，整合 build）重用。
//
//  Stage 5 本身完全不受影響、繼續維持獨立可建置——這裡是「複製 + 擴充」，
//  不是「搬移」，故意不刪 Stage 5 那段程式碼，保留它作為 LCD 單獨驗證用。
//
//  跟 Stage 5 的差異：表情從 6 種擴充成 9 種，對齊
//  ai-pc-agent/protocol.py 的 EXPRESSIONS（neutral/happy/joy/love/sad/
//  sleepy/surprised/thinking/worried）。新增的 3 種（neutral/thinking/
//  worried）畫法沒有實機驗證過，比照專案既有慣例先標成未驗證，等實機
//  測試回報。
// ============================================================
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include "board_config.h"

static Adafruit_ST7735 lcdTft(PIN_LCD_CS, PIN_LCD_DC, PIN_LCD_RST);

// 1 = 橫放；畫面上下顛倒就改成 3
static const uint8_t LCD_ROTATION = 1;

static const uint16_t LCD_COLOR_BG    = ST77XX_BLACK;
static const uint16_t LCD_COLOR_FG    = ST77XX_WHITE;
static const uint16_t LCD_COLOR_FRAME = ST77XX_YELLOW;
static const uint16_t LCD_COLOR_BLUSH = 0xFCB6;   // 粉紅腮紅 (255,150,180)
static const uint16_t LCD_COLOR_HEART = 0xFAD1;   // 桃紅愛心 (255,90,140)
static const uint16_t LCD_COLOR_TEAR  = 0x865F;   // 淺藍眼淚 (130,200,255)
static const uint16_t LCD_COLOR_BROW  = 0xFD20;   // 橘色眉毛 (255,165,0)

// 順序對齊 ai-pc-agent/protocol.py 的 EXPRESSIONS，方便 WS 收到字串直接查表。
enum LcdFace {
  LCD_FACE_NEUTRAL, LCD_FACE_HAPPY, LCD_FACE_JOY, LCD_FACE_LOVE, LCD_FACE_SAD,
  LCD_FACE_SLEEPY, LCD_FACE_SURPRISED, LCD_FACE_THINKING, LCD_FACE_WORRIED,
  LCD_FACE_COUNT
};
static const char *LCD_FACE_NAMES[LCD_FACE_COUNT] = {
  "neutral", "happy", "joy", "love", "sad", "sleepy", "surprised", "thinking", "worried"
};

// 找不到就回 LCD_FACE_NEUTRAL（安全預設），不讓打錯字的表情名讓 LCD 卡住。
static LcdFace lcdFaceFromName(const char *name) {
  for (int i = 0; i < LCD_FACE_COUNT; i++) {
    if (strcmp(name, LCD_FACE_NAMES[i]) == 0) return (LcdFace)i;
  }
  return LCD_FACE_NEUTRAL;
}

// ---- 版面（以 160x128 橫放為準，跟 Stage 5 完全一致）----
static const int LCD_FRAME_INSET = 4;
static const int LCD_FRAME_T     = 2;
static const int LCD_INNER_PAD   = LCD_FRAME_INSET + LCD_FRAME_T + 2;
static const int LCD_EYE_RX      = 11;
static const int LCD_EYE_RY      = 15;
static const int LCD_EYE_DX      = 26;
static const int LCD_EYE_Y       = 44;
static const int LCD_CHEEK_TOP   = LCD_EYE_Y + LCD_EYE_RY + 3;
static const int LCD_MOUTH_Y     = 70;
static const int LCD_TEXT_TOP    = 86;

static int  s_lcdW = 0, s_lcdH = 0, s_lcdCx = 0;
static LcdFace s_lcdFace = LCD_FACE_NEUTRAL;
static String  s_lcdText = "Hi! I'm here";
static bool    s_lcdEyesClosed = false;

static void lcdDrawDashedFrame() {
  const int x0 = LCD_FRAME_INSET, y0 = LCD_FRAME_INSET;
  const int x1 = s_lcdW - 1 - LCD_FRAME_INSET, y1 = s_lcdH - 1 - LCD_FRAME_INSET;
  const int DASH = 8, GAP = 5;
  for (int x = x0; x <= x1; x += DASH + GAP) {
    const int len = min(DASH, x1 - x + 1);
    lcdTft.fillRect(x, y0, len, LCD_FRAME_T, LCD_COLOR_FRAME);
    lcdTft.fillRect(x, y1 - LCD_FRAME_T + 1, len, LCD_FRAME_T, LCD_COLOR_FRAME);
  }
  for (int y = y0; y <= y1; y += DASH + GAP) {
    const int len = min(DASH, y1 - y + 1);
    lcdTft.fillRect(x0, y, LCD_FRAME_T, len, LCD_COLOR_FRAME);
    lcdTft.fillRect(x1 - LCD_FRAME_T + 1, y, LCD_FRAME_T, len, LCD_COLOR_FRAME);
  }
}

// corner 位元：1=左上 2=右上 4=右下 8=左下
static void lcdThickArc(int x, int y, int r, uint8_t corners, uint16_t color) {
  for (int t = 0; t < 3; t++) lcdTft.drawCircleHelper(x, y, r - t, corners, color);
}

static void lcdDrawOneEye(int ex, bool isLeft) {
  if (s_lcdEyesClosed) {
    lcdTft.fillRoundRect(ex - LCD_EYE_RX, LCD_EYE_Y - 1, 2 * LCD_EYE_RX, 3, 1, LCD_COLOR_FG);
    return;
  }
  switch (s_lcdFace) {
    case LCD_FACE_JOY:
      lcdThickArc(ex, LCD_EYE_Y + 5, 10, 1 | 2, LCD_COLOR_FG);
      break;
    case LCD_FACE_SLEEPY:
      lcdThickArc(ex, LCD_EYE_Y - 4, 10, 4 | 8, LCD_COLOR_FG);
      break;
    case LCD_FACE_LOVE:
      lcdTft.fillCircle(ex - 6, LCD_EYE_Y - 4, 6, LCD_COLOR_HEART);
      lcdTft.fillCircle(ex + 6, LCD_EYE_Y - 4, 6, LCD_COLOR_HEART);
      lcdTft.fillTriangle(ex - 12, LCD_EYE_Y - 2, ex + 12, LCD_EYE_Y - 2, ex, LCD_EYE_Y + 11, LCD_COLOR_HEART);
      lcdTft.fillCircle(ex - 7, LCD_EYE_Y - 6, 2, LCD_COLOR_FG);
      break;
    case LCD_FACE_SURPRISED:
      lcdTft.fillCircle(ex, LCD_EYE_Y, LCD_EYE_RX + 2, LCD_COLOR_FG);
      lcdTft.fillCircle(ex, LCD_EYE_Y + 2, 5, LCD_COLOR_BG);
      lcdTft.fillCircle(ex - 2, LCD_EYE_Y, 1, LCD_COLOR_FG);
      break;
    case LCD_FACE_SAD: {
      lcdTft.fillRoundRect(ex - LCD_EYE_RX, LCD_EYE_Y - LCD_EYE_RY, 2 * LCD_EYE_RX, 2 * LCD_EYE_RY, LCD_EYE_RX, LCD_COLOR_FG);
      const int top = LCD_EYE_Y - LCD_EYE_RY - 1;
      if (isLeft) {
        lcdTft.fillTriangle(ex - LCD_EYE_RX - 1, top, ex + LCD_EYE_RX + 1, top, ex - LCD_EYE_RX - 1, LCD_EYE_Y + 2, LCD_COLOR_BG);
      } else {
        lcdTft.fillTriangle(ex + LCD_EYE_RX + 1, top, ex - LCD_EYE_RX - 1, top, ex + LCD_EYE_RX + 1, LCD_EYE_Y + 2, LCD_COLOR_BG);
      }
      break;
    }
    case LCD_FACE_THINKING:
      // 一般大眼 + 瞳孔往上偏移，像在想事情——沒有實機驗證過視覺效果。
      lcdTft.fillRoundRect(ex - LCD_EYE_RX, LCD_EYE_Y - LCD_EYE_RY, 2 * LCD_EYE_RX, 2 * LCD_EYE_RY, LCD_EYE_RX, LCD_COLOR_FG);
      lcdTft.fillCircle(ex + (isLeft ? 3 : -3), LCD_EYE_Y - 4, 3, LCD_COLOR_BG);
      break;
    case LCD_FACE_WORRIED:
      // 一般大眼，但下面畫一條眉毛壓低，製造擔心的皺眉感——沒有實機驗證過視覺效果。
      lcdTft.fillRoundRect(ex - LCD_EYE_RX, LCD_EYE_Y - LCD_EYE_RY, 2 * LCD_EYE_RX, 2 * LCD_EYE_RY, LCD_EYE_RX, LCD_COLOR_FG);
      if (isLeft) {
        lcdTft.drawLine(ex - LCD_EYE_RX - 2, LCD_EYE_Y - LCD_EYE_RY - 6, ex + LCD_EYE_RX - 4, LCD_EYE_Y - LCD_EYE_RY - 2, LCD_COLOR_BROW);
      } else {
        lcdTft.drawLine(ex + LCD_EYE_RX + 2, LCD_EYE_Y - LCD_EYE_RY - 6, ex - LCD_EYE_RX + 4, LCD_EYE_Y - LCD_EYE_RY - 2, LCD_COLOR_BROW);
      }
      break;
    case LCD_FACE_NEUTRAL:
      // 比 happy 扁一點的橢圓，代表平靜、沒有特別情緒。
      lcdTft.fillRoundRect(ex - LCD_EYE_RX, LCD_EYE_Y - LCD_EYE_RY / 2, 2 * LCD_EYE_RX, LCD_EYE_RY, LCD_EYE_RY / 2, LCD_COLOR_FG);
      break;
    default:  // LCD_FACE_HAPPY
      lcdTft.fillRoundRect(ex - LCD_EYE_RX, LCD_EYE_Y - LCD_EYE_RY, 2 * LCD_EYE_RX, 2 * LCD_EYE_RY, LCD_EYE_RX, LCD_COLOR_FG);
      break;
  }
}

static void lcdDrawEyes() {
  const int pad = LCD_EYE_RX + 4;
  // 眉毛（worried）畫在眼睛區上緣以外一點，清除範圍要往上多留幾個像素，
  // 不然換回其他表情時眉毛線殘留在螢幕上。
  lcdTft.fillRect(s_lcdCx - LCD_EYE_DX - pad, LCD_EYE_Y - LCD_EYE_RY - 10,
               2 * (LCD_EYE_DX + pad), LCD_CHEEK_TOP - (LCD_EYE_Y - LCD_EYE_RY - 10), LCD_COLOR_BG);
  lcdDrawOneEye(s_lcdCx - LCD_EYE_DX, true);
  lcdDrawOneEye(s_lcdCx + LCD_EYE_DX, false);
}

static void lcdDrawLowerFace() {
  const int pad = LCD_EYE_RX + 10;
  lcdTft.fillRect(s_lcdCx - LCD_EYE_DX - pad, LCD_CHEEK_TOP, 2 * (LCD_EYE_DX + pad), LCD_TEXT_TOP - LCD_CHEEK_TOP, LCD_COLOR_BG);

  const int cheekY = LCD_CHEEK_TOP + 2;
  if (s_lcdFace == LCD_FACE_SAD) {
    const int tx = s_lcdCx - LCD_EYE_DX - 6;
    lcdTft.fillTriangle(tx - 3, cheekY + 3, tx + 3, cheekY + 3, tx, cheekY - 3, LCD_COLOR_TEAR);
    lcdTft.fillCircle(tx, cheekY + 5, 3, LCD_COLOR_TEAR);
  } else if (s_lcdFace != LCD_FACE_NEUTRAL && s_lcdFace != LCD_FACE_WORRIED) {
    lcdTft.fillRoundRect(s_lcdCx - LCD_EYE_DX - 12, cheekY, 14, 6, 3, LCD_COLOR_BLUSH);
    lcdTft.fillRoundRect(s_lcdCx + LCD_EYE_DX - 2,  cheekY, 14, 6, 3, LCD_COLOR_BLUSH);
  }

  switch (s_lcdFace) {
    case LCD_FACE_HAPPY:
    case LCD_FACE_LOVE:
      for (int t = 0; t < 2; t++) {
        lcdTft.drawCircleHelper(s_lcdCx - 4, LCD_MOUTH_Y - 2 + t, 4, 4 | 8, LCD_COLOR_FG);
        lcdTft.drawCircleHelper(s_lcdCx + 4, LCD_MOUTH_Y - 2 + t, 4, 4 | 8, LCD_COLOR_FG);
      }
      break;
    case LCD_FACE_JOY:
      lcdTft.fillCircle(s_lcdCx, LCD_MOUTH_Y - 3, 7, LCD_COLOR_FG);
      lcdTft.fillRect(s_lcdCx - 8, LCD_MOUTH_Y - 11, 17, 8, LCD_COLOR_BG);
      lcdTft.fillCircle(s_lcdCx, LCD_MOUTH_Y + 2, 2, LCD_COLOR_BLUSH);
      break;
    case LCD_FACE_SAD:
      for (int t = 0; t < 2; t++) {
        lcdTft.drawCircleHelper(s_lcdCx - 4, LCD_MOUTH_Y + 3 + t, 4, 1 | 2, LCD_COLOR_FG);
        lcdTft.drawCircleHelper(s_lcdCx + 4, LCD_MOUTH_Y + 3 + t, 4, 1 | 2, LCD_COLOR_FG);
      }
      break;
    case LCD_FACE_SURPRISED:
      lcdTft.drawCircle(s_lcdCx, LCD_MOUTH_Y, 5, LCD_COLOR_FG);
      lcdTft.drawCircle(s_lcdCx, LCD_MOUTH_Y, 4, LCD_COLOR_FG);
      break;
    case LCD_FACE_THINKING:
      // 嘴巴偏向一側的小圓，像是抿著嘴思考——沒有實機驗證過視覺效果。
      lcdTft.fillCircle(s_lcdCx + 5, LCD_MOUTH_Y, 3, LCD_COLOR_FG);
      break;
    case LCD_FACE_WORRIED:
      // 波浪形嘴巴（幾段短線連起來），代表緊張——沒有實機驗證過視覺效果。
      for (int i = -6; i < 6; i += 3) {
        lcdTft.drawLine(s_lcdCx + i, LCD_MOUTH_Y + (((i / 3) % 2 == 0) ? -2 : 2),
                     s_lcdCx + i + 3, LCD_MOUTH_Y + (((i / 3) % 2 == 0) ? 2 : -2), LCD_COLOR_FG);
      }
      break;
    case LCD_FACE_NEUTRAL:
      lcdTft.drawFastHLine(s_lcdCx - 5, LCD_MOUTH_Y, 10, LCD_COLOR_FG);
      break;
    default:  // LCD_FACE_SLEEPY
      lcdTft.fillCircle(s_lcdCx, LCD_MOUTH_Y, 3, LCD_COLOR_FG);
      break;
  }
}

static void lcdDrawText() {
  const int areaX = LCD_INNER_PAD, areaW = s_lcdW - 2 * LCD_INNER_PAD;
  const int areaY = LCD_TEXT_TOP,  areaH = s_lcdH - LCD_INNER_PAD - LCD_TEXT_TOP;
  lcdTft.fillRect(areaX, areaY, areaW, areaH, LCD_COLOR_BG);

  int size = ((int)s_lcdText.length() * 12 <= areaW) ? 2 : 1;
  const int maxChars = areaW / (6 * size);
  String shown = s_lcdText.substring(0, maxChars);

  const int textW = (int)shown.length() * 6 * size;
  const int textH = 8 * size;
  lcdTft.setTextWrap(false);
  lcdTft.setTextSize(size);
  lcdTft.setTextColor(LCD_COLOR_FG, LCD_COLOR_BG);
  lcdTft.setCursor(areaX + (areaW - textW) / 2, areaY + (areaH - textH) / 2);
  lcdTft.print(shown);
}

static void lcdShowFace(LcdFace f)             { s_lcdFace = f; s_lcdEyesClosed = false; lcdDrawEyes(); lcdDrawLowerFace(); }
static void lcdShowText(const String &text)    { s_lcdText = text; lcdDrawText(); }
static void lcdShowFaceByName(const char *name) { lcdShowFace(lcdFaceFromName(name)); }

static uint32_t s_lcdNextBlinkAt = 0;
static uint32_t s_lcdBlinkUntil  = 0;

static void lcdUpdateBlink(uint32_t now) {
  if (!s_lcdEyesClosed) {
    if (now >= s_lcdNextBlinkAt && s_lcdFace != LCD_FACE_SLEEPY && s_lcdFace != LCD_FACE_JOY) {
      s_lcdEyesClosed = true;
      s_lcdBlinkUntil = now + 160;
      lcdDrawEyes();
    }
  } else if (now >= s_lcdBlinkUntil) {
    s_lcdEyesClosed  = false;
    s_lcdNextBlinkAt = now + 2500 + (esp_random() % 2500);
    lcdDrawEyes();
  }
}

static void lcdInit() {
  lcdTft.initR(INITR_BLACKTAB);
  lcdTft.setRotation(LCD_ROTATION);
  s_lcdW  = lcdTft.width();
  s_lcdH  = lcdTft.height();
  s_lcdCx = s_lcdW / 2;

  lcdTft.fillScreen(LCD_COLOR_BG);
  lcdDrawDashedFrame();
  lcdShowFace(s_lcdFace);
  lcdShowText(s_lcdText);

  s_lcdNextBlinkAt = millis() + 2000;
}
