# logs/

實機錄下來的資料放這裡。

命名規則，來源必須從檔名就看得出來：

- `real_YYYYMMDD_HHMM_<stage>.csv` — 真的從 ESP32 讀到的
- `mock_...csv` — 程式產生的假資料（測 dashboard 用）
- `sample_...csv` — 手動貼的範例

**不要把 mock 和 real 混在同一個檔案。**

CSV 欄位（Stage 6 定案後採用）：

```
schema_version,seq,t_ms,fsr1_raw,fsr2_raw,ax,ay,az,gx,gy,gz,imu_ok
```

單位另附 metadata 檔說明。
**無效讀值不要假造成正常的 0** — 用空欄或哨兵值，並讓 `imu_ok` 反映狀態。

目前：尚無任何檔案。
