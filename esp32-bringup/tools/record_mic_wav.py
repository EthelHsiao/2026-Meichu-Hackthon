"""從 ESP32 的 s12_mic_wav 階段讀取 I2S 麥克風的原始 PCM 音訊，
存成一個可以直接雙擊播放的 .wav 檔。

這支腳本在「你自己的電腦」上執行（不是在 Claude 的沙盒裡），因為只有
你電腦能直接接觸到 ESP32 的 COM port。

用法（先確認 PlatformIO 的 Serial Monitor 沒有同時開著那個 COM port，
Windows 一次只能有一個程式獨佔序列埠）：

    pip install -r tools/requirements.txt
    python tools/record_mic_wav.py COM5 --seconds 5

COM 埠代號換成你自己的——Build/Upload 時 PlatformIO 終端機會印出來，
或去「裝置管理員」→「連接埠 (COM 和 LPT)」查。
"""
import argparse
import array
import sys
import time
import wave

try:
    import serial
except ImportError:
    print("缺少 pyserial，先執行：pip install -r tools/requirements.txt", file=sys.stderr)
    sys.exit(1)

SAMPLE_RATE = 16000
SAMPLE_WIDTH_BYTES = 2   # 16-bit
CHANNELS = 1
BAUD = 921600            # 要跟 board_config.h 的 MIC_WAV_STREAM_BAUD 一致
HEADER_LINES = 3         # ESP32 端固定先印 3 行文字說明，見 main.cpp Step 12


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="ESP32 的 COM port，例如 COM5")
    ap.add_argument("--seconds", type=float, default=5.0, help="錄幾秒，預設 5 秒")
    ap.add_argument("--out", default="mic_test.wav", help="輸出的 wav 檔名，預設 mic_test.wav")
    args = ap.parse_args()

    print(f"開啟 {args.port} @ {BAUD} baud ...")
    try:
        ser = serial.Serial(args.port, BAUD, timeout=2)
    except serial.SerialException as exc:
        print(f"打不開 {args.port}：{exc}", file=sys.stderr)
        print("常見原因：PlatformIO 的 Serial Monitor 還開著佔用同一個埠，先關掉它再跑這支腳本。", file=sys.stderr)
        sys.exit(1)

    print(f"等待 ESP32 端的說明文字（{HEADER_LINES} 行）...")
    for _ in range(HEADER_LINES):
        line = ser.readline()
        if not line:
            print("等不到文字，檢查 ESP32 是不是真的在跑 s12_mic_wav、板子有沒有重開機。", file=sys.stderr)
            ser.close()
            sys.exit(1)
        print("  <-", line.decode("utf-8", errors="replace").strip())

    total_bytes = int(args.seconds * SAMPLE_RATE * SAMPLE_WIDTH_BYTES)
    print(f"開始錄音 {args.seconds} 秒（約 {total_bytes} bytes）——現在對著麥克風說話/拍手！")

    # ESP32 端印完 3 行說明文字之後，會刻意停頓約 3 秒才開始送真正的 PCM
    # （見 main.cpp Step 12 的 delay(3000)），這段時間讀不到資料是正常的，
    # 不能一次讀空就判定失敗——STALL_LIMIT 拉寬容忍這段已知的靜默期，
    # 真的連續這麼久收不到才算異常。
    STALL_LIMIT_S = 6.0
    pcm = bytearray()
    t0 = time.time()
    last_data_time = t0
    while len(pcm) < total_bytes:
        chunk = ser.read(4096)
        now = time.time()
        if chunk:
            pcm.extend(chunk)
            last_data_time = now
        elif now - last_data_time > STALL_LIMIT_S:
            print(f"警告：連續 {STALL_LIMIT_S:.0f} 秒沒收到任何資料，可能接線鬆脫或板子當掉了。", file=sys.stderr)
            break
        if now - t0 > args.seconds + STALL_LIMIT_S + 5:
            print("超時，提前結束。", file=sys.stderr)
            break

    ser.close()
    pcm = bytes(pcm[:total_bytes])

    # ESP32 端為了避免削峰失真，刻意錄得偏小聲；這裡自動偵測整段錄音的
    # 峰值，放大到接近滿量程再存檔，不用回頭猜韌體那個位移量對不對。
    samples = array.array("h")   # "h" = signed 16-bit，跟韌體送出來的格式一致
    samples.frombytes(pcm)
    peak = max((abs(s) for s in samples), default=0)

    if peak == 0:
        print("警告：整段錄音峰值是 0，代表完全沒收到有效訊號（不是音量太小的問題）。", file=sys.stderr)
        print("先確認麥克風接線（尤其 WS/SCK/SD 有沒有接對），或重跑 s11_mic 確認底層讀值正常。", file=sys.stderr)
    else:
        target_peak = int(32767 * 0.9)
        gain = target_peak / peak
        if gain > 1.02:   # 差不多就不用放大，避免無意義的小數運算
            for i, s in enumerate(samples):
                v = int(s * gain)
                if v > 32767:
                    v = 32767
                elif v < -32768:
                    v = -32768
                samples[i] = v
            print(f"偵測到峰值音量為滿量程的 {peak/32767*100:.1f}%，自動放大 {gain:.1f} 倍。")
        else:
            print(f"峰值音量為滿量程的 {peak/32767*100:.1f}%，已經夠大聲，不需要再放大。")
        pcm = samples.tobytes()

    with wave.open(args.out, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH_BYTES)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)

    got_seconds = len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH_BYTES)
    print(f"完成，存成 {args.out}（{len(pcm)} bytes，約 {got_seconds:.1f} 秒）")
    print("直接用檔案總管雙擊播放，或拖進瀏覽器分頁，應該就能聽到/看到波形。")
    if got_seconds < args.seconds * 0.8:
        print("實際錄到的秒數比要求的短不少，可能中途漏資料，建議重錄一次確認。", file=sys.stderr)


if __name__ == "__main__":
    main()
