"""產生 LCD 用的繁中 12px 字型 include/font_tc12.h（u8g2 格式）。

字型：Fusion Pixel 12px Proportional zh_hant（SIL OFL 1.1，https://github.com/TakWolf/fusion-pixel-font）
字集：ASCII + Big5 符號區 + Big5 常用字（A440–C67E，5401 字）。罕用字不收，會顯示成空白。

用法：
  python3 tools/make_font_tc12.py <fusion-pixel-12px-proportional-zh_hant.bdf> <bdfconv 執行檔>
bdfconv 在 u8g2 原始碼的 tools/font/bdfconv（macOS 用 `cc -O2 -w -o bdfconv *.c` 編）。
"""
import pathlib
import subprocess
import sys
import tempfile


def big5_range(lead_lo, lead_hi, last=None):
    chars = []
    for lead in range(lead_lo, lead_hi + 1):
        for trail in list(range(0x40, 0x7F)) + list(range(0xA1, 0xFF)):
            if last and (lead, trail) > last:
                return chars
            try:
                chars.append(bytes([lead, trail]).decode("big5"))
            except UnicodeDecodeError:
                pass
    return chars


def main():
    bdf, bdfconv = sys.argv[1], sys.argv[2]
    chars = [chr(c) for c in range(32, 127)]
    chars += big5_range(0xA1, 0xA3)                    # 全形標點、符號
    chars += big5_range(0xA4, 0xC6, last=(0xC6, 0x7E))  # 常用字
    out = pathlib.Path(__file__).resolve().parent.parent / "include" / "font_tc12.h"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write("".join(dict.fromkeys(chars)))
    subprocess.run([bdfconv, "-f", "1", "-b", "0", "-u", f.name, "-n", "u8g2_font_tc12", "-o", str(out), bdf], check=True)
    print(f"{len(set(chars))} 字 -> {out}")


if __name__ == "__main__":
    main()
