"""debug_api.py 的 dashboard 頁面（見 docs/api.html §⑧）。獨立成檔案純粹是讓
debug_api.py 保持好讀；沒有外部依賴，全部內嵌 CSS/JS，跟 mi300-deploy 的
DASHBOARD_HTML 走同一個風格。只給本機/內網用。"""

DASHBOARD_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>AIPC 除錯 Dashboard</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang TC", "Noto Sans TC", sans-serif;
         background: #0f1115; color: #e6e6e6; margin: 0; padding: 20px; }
  h1 { font-size: 20px; font-weight: 600; margin: 0 0 4px; }
  .sub { color: #9aa0a6; font-size: 13px; margin-bottom: 16px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }
  .card { background: #1a1d24; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; }
  .card h2 { font-size: 13px; color: #9aa0a6; margin: 0 0 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .04em; }
  .status-row { display: flex; flex-wrap: wrap; gap: 18px; font-size: 14px; }
  .status-item { display: flex; align-items: center; gap: 6px; }
  .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: #6b7280; }
  .dot.ok { background: #22c55e; }
  .dot.bad { background: #ef4444; }
  label { display: block; font-size: 12px; color: #9aa0a6; margin: 10px 0 4px; }
  input, select, textarea, button { font: inherit; }
  input, select, textarea {
    width: 100%; background: #12141a; border: 1px solid #2b2f3a; border-radius: 6px;
    color: #e6e6e6; padding: 6px 8px;
  }
  textarea { min-height: 56px; resize: vertical; }
  button {
    margin-top: 10px; background: #2563eb; color: white; border: none; border-radius: 6px;
    padding: 8px 14px; cursor: pointer; font-size: 13px;
  }
  button:hover { background: #1d4ed8; }
  button.secondary { background: #374151; }
  button.secondary:hover { background: #4b5563; }
  .form-block { border-top: 1px solid #262a33; padding-top: 12px; margin-top: 12px; }
  .form-block:first-child { border-top: none; padding-top: 0; margin-top: 0; }
  .checkbox-row { display: flex; align-items: center; gap: 6px; margin-top: 10px; }
  .checkbox-row input { width: auto; }
  .feed { max-height: 640px; overflow-y: auto; }
  .entry { border-top: 1px solid #262a33; padding: 10px 0; display: flex; gap: 10px; }
  .entry:first-child { border-top: none; }
  .entry img { width: 72px; height: 54px; object-fit: cover; border-radius: 6px; background: #000; flex-shrink: 0; }
  .entry-body { flex: 1; min-width: 0; }
  .entry-head { display: flex; gap: 8px; align-items: baseline; font-size: 12px; color: #9aa0a6; }
  .kind { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 999px; }
  .kind.screen_observation { background: #164e63; color: #67e8f9; }
  .kind.chat_reply { background: #713f12; color: #fde68a; }
  .kind.homework_analysis { background: #4c1d95; color: #ddd6fe; }
  .kind.touch { background: #14532d; color: #86efac; }
  .kind.stt_final { background: #0c4a6e; color: #7dd3fc; }
  .kind.esp32_say { background: #3f2d1a; color: #fbbf24; }
  .kind.chatgpt_send { background: #1e3a5f; color: #93c5fd; }
  .kind.cam_snapshot { background: #422006; color: #fdba74; }
  .entry-summary { font-size: 14px; margin: 4px 0; white-space: pre-wrap; word-break: break-word; }
  details { margin-top: 4px; }
  details summary { cursor: pointer; font-size: 12px; color: #9aa0a6; }
  details pre { background: #0d0f13; padding: 8px 10px; border-radius: 6px; font-size: 12px;
                overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 4px 6px; border-top: 1px solid #262a33; }
  th { color: #9aa0a6; font-weight: 500; }
  .empty { color: #6b7280; font-size: 13px; padding: 8px 0; }
  .msg { font-size: 12px; margin-top: 6px; min-height: 14px; }
  .msg.err { color: #f87171; }
  .msg.ok { color: #86efac; }
</style>
</head>
<body>
  <h1>AIPC 除錯 Dashboard</h1>
  <div class="sub">本機測試/除錯用，見 docs/api.html §⑧ 與 debug_api.py。每 3 秒自動刷新。</div>

  <div class="card">
    <h2>狀態</h2>
    <div class="status-row" id="status">連線中...</div>
  </div>

  <div class="card">
    <h2>目前 LCD 應該顯示什麼（只在成功送出指令時更新，不是螢幕的即時畫面）</h2>
    <div id="lcdState"><div class="empty">還沒送過任何表情/台詞</div></div>
  </div>

  <div class="card">
    <h2>即時感測器（FSR / IMU，每 300ms 刷新，不進記憶庫）</h2>
    <div id="telemetry"><div class="empty">還沒收到 ESP32 telemetry</div></div>
  </div>

  <div class="card">
    <h2>即時麥克風音量 / VAD（STT 服務回報，每 300ms 刷新）</h2>
    <div id="sttLevel"><div class="empty">還沒收到 STT 音量回報</div></div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>觸發測試（不需要實體硬體）</h2>

      <div class="form-block">
        <label>手勢事件</label>
        <select id="gestureKind">
          <option value="double_tap">double_tap（觸發作業拍照流程）</option>
          <option value="squeeze">squeeze</option>
          <option value="pat">pat</option>
          <option value="shake">shake</option>
          <option value="lift">lift</option>
          <option value="putdown">putdown</option>
        </select>
        <button onclick="sendGesture()">送出手勢</button>
        <div class="msg" id="msg-gesture"></div>
      </div>

      <div class="form-block">
        <label>直接換表情（不用等 MI300 選到，demo 保底用）</label>
        <select id="exprKind">
          <option value="neutral">neutral</option>
          <option value="idle">idle（預設待機）</option>
          <option value="love">love</option>
          <option value="sad">sad</option>
          <option value="sleepy">sleepy</option>
          <option value="surprised">surprised</option>
          <option value="thinking">thinking</option>
          <option value="worried">worried</option>
          <option value="dizzy">dizzy</option>
        </select>
        <button onclick="sendExpr()">換表情</button>
        <div class="msg" id="msg-expr"></div>
      </div>

      <div class="form-block">
        <label>模擬使用者說話</label>
        <input id="utteranceText" placeholder="這個到底怎麼修" />
        <button onclick="sendUtterance()">送出語音（觸發對話回覆）</button>
        <div class="msg" id="msg-utterance"></div>
      </div>

      <div class="form-block">
        <label>截圖分析</label>
        <button onclick="sendScreenshot()">立刻截圖分析（不等排程）</button>
        <div class="msg" id="msg-screenshot"></div>
      </div>

      <div class="form-block">
        <label>作業拍照分析</label>
        <input id="homeworkImage" type="file" accept="image/*" />
        <textarea id="homeworkTranscript" placeholder="這題我算了好久都算錯..."></textarea>
        <div class="checkbox-row">
          <input id="homeworkSend" type="checkbox" />
          <label style="margin:0" for="homeworkSend">同時送到 ChatGPT（Playwright）</label>
        </div>
        <button onclick="sendHomework()">送出分析</button>
        <div class="msg" id="msg-homework"></div>
      </div>
    </div>

    <div class="card">
      <h2>最近記憶（memories 表）</h2>
      <div class="form-block" style="border-top:none; padding-top:0; margin-top:0; margin-bottom:12px;">
        <button class="secondary" onclick="seedMemory()">植入假記憶（測試用）</button>
        <button class="secondary" onclick="clearMemory()" style="background:#7f1d1d;">清空所有記憶</button>
        <div class="msg" id="msg-memory-admin"></div>
      </div>
      <div id="memory"><div class="empty">還沒有資料</div></div>
    </div>
  </div>

  <div class="card">
    <h2>測試記憶檢索（hybrid vector + BM25）</h2>
    <div class="sub" style="margin:0 0 8px;">輸入一句查詢，看實際會撈出哪幾筆、分數怎麼算——用來判斷 retrieval 排序合不合理，不用真的跑一次完整對話。植入假記憶之後再查會比較有東西可以比較。</div>
    <input id="retrieveQuery" placeholder="例如：KeyError 或 累" style="width:auto; display:inline-block; min-width:240px;" />
    <button onclick="sendRetrieve()">查詢</button>
    <div class="msg" id="msg-retrieve"></div>
    <div id="retrieveResult" style="margin-top:10px;"></div>
  </div>

  <div class="card">
    <h2>傳了什麼、收到什麼（trace）</h2>
    <div class="feed" id="feed"><div class="empty">還沒有任何呼叫紀錄</div></div>
  </div>

<script>
async function getJson(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function esc(s) { return String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

async function refreshStatus() {
  const el = document.getElementById('status');
  try {
    const s = await getJson('/debug/status');
    let touch = '（無）';
    let touchJustFired = false;
    if (s.last_touch) {
      touch = `${s.last_touch.kind}（強度 ${Number(s.last_touch.strength).toFixed(1)}）`;
      if (s.last_touch_ts) {
        const secAgo = (Date.now() - new Date(s.last_touch_ts).getTime()) / 1000;
        touch += secAgo < 60 ? `　${secAgo.toFixed(1)} 秒前` : `　${esc(s.last_touch_ts)}`;
        touchJustFired = secAgo < 2;   // 2 秒內＝剛剛觸發，閃一下讓你確定「有沒有觸發」
      }
    }
    let micAgo = '從未收到';
    if (s.last_mic_ts) {
      const secAgo = (Date.now() - new Date(s.last_mic_ts).getTime()) / 1000;
      micAgo = secAgo < 60 ? `${secAgo.toFixed(1)} 秒前` : esc(s.last_mic_ts);
    }
    el.innerHTML = `
      <span class="status-item"><span class="dot ${s.esp32_ws_connected ? 'ok' : 'bad'}"></span>ESP32 WebSocket</span>
      <span class="status-item"><span class="dot ${s.mi300_reachable ? 'ok' : 'bad'}"></span>MI300</span>
      <span class="status-item"><span class="dot ${s.stt_connected ? 'ok' : 'bad'}"></span>STT 服務</span>
      <span class="status-item" style="${touchJustFired ? 'background:#14532d; padding:2px 8px; border-radius:6px;' : ''}">最近手勢：${esc(touch)}</span>
      <span class="status-item">麥克風最後收到：${micAgo}（累計 ${s.mic_frames_total ?? 0} 包）</span>
      <span class="status-item">最後寫入記憶：${esc(s.last_memory_write_ts || '（無）')}</span>
      <span class="status-item">AIPC 版本：${esc(s.aipc_commit || '未知')}</span>
      <span class="status-item">MI300 版本：${esc(s.mi300_deploy_sha || '未知')}（${esc(s.mi300_deploy_time || '未知')}）</span>`;
  } catch (e) {
    el.textContent = '連線失敗：' + e.message;
  }
}

let gestureConfig = {};   // 從 /debug/gesture_config 讀，永遠反映 config.py 目前實際生效的門檻，不寫死
async function loadGestureConfig() {
  try { gestureConfig = await getJson('/debug/gesture_config'); } catch (e) { /* 沒拿到就用預設顯示，不擋頁面 */ }
}

async function refreshTelemetry() {
  const el = document.getElementById('telemetry');
  try {
    const t = await getJson('/debug/telemetry');
    if (!t) { el.innerHTML = '<div class="empty">還沒收到 ESP32 telemetry</div>'; return; }
    const fsr = t.fsr || {};
    const imu = t.imu || {};
    const raw = fsr.raw || [];
    const pressRaw = gestureConfig.fsr_press_raw ?? 250;
    const fsrRows = fsr.enabled === false
      ? '<tr><td colspan="3">FSR 未啟用</td></tr>'
      : raw.map((v, i) => `<tr><td>FSR${i + 1} raw</td><td>${v}</td><td>${
          v > pressRaw ? '<b style="color:#86efac">按下</b>' : '（未按）'
        }（門檻 ${pressRaw}）</td></tr>`).join('');
    const accel = imu.accel_m_s2 || [];
    const gyro = imu.gyro_rad_s || [];
    const accelMag = accel.length === 3 ? Math.sqrt(accel[0]**2 + accel[1]**2 + accel[2]**2) : null;
    el.innerHTML = `<table>
      <tr><th>seq</th><td colspan="2">${t.seq}</td></tr>
      ${fsrRows}
      <tr><th>IMU 狀態</th><td colspan="2">${esc(imu.status || '')}</td></tr>
      ${imu.ok ? `
      <tr><td>accel (m/s²)</td><td colspan="2">${esc(accel.map(v => v.toFixed(2)).join(', '))}${
        accelMag !== null ? `　|a|=${accelMag.toFixed(2)}（搖晃門檻 SHAKE_ACCEL_P2P=${gestureConfig.shake_accel_p2p ?? '?'}，看的是視窗內峰對峰變化，不是單筆這個值）` : ''
      }</td></tr>
      <tr><td>gyro (rad/s)</td><td colspan="2">${esc(gyro.map(v => v.toFixed(3)).join(', '))}</td></tr>
      <tr><td>溫度</td><td colspan="2">${(imu.temperature_c ?? 0).toFixed(1)} °C</td></tr>` : ''}
    </table>`;
  } catch (e) {
    el.innerHTML = `<div class="empty">連線失敗：${esc(e.message)}</div>`;
  }
}

async function refreshLcdState() {
  const el = document.getElementById('lcdState');
  try {
    const s = await getJson('/debug/status');
    if (!s.lcd_updated_ts) { el.innerHTML = '<div class="empty">還沒送過任何表情/台詞</div>'; return; }
    const secAgo = (Date.now() - new Date(s.lcd_updated_ts).getTime()) / 1000;
    el.innerHTML = `
      <div style="font-size:15px;"><b>表情：${esc(s.lcd_expr || '')}</b></div>
      <div style="font-size:14px; margin-top:4px; white-space:pre-wrap;">台詞：${esc(s.lcd_text || '（無）')}</div>
      <div class="sub" style="margin:6px 0 0;">最後更新：${secAgo < 60 ? secAgo.toFixed(1) + ' 秒前' : esc(s.lcd_updated_ts)}</div>`;
  } catch (e) {
    el.innerHTML = `<div class="empty">連線失敗：${esc(e.message)}</div>`;
  }
}

async function refreshSttLevel() {
  const el = document.getElementById('sttLevel');
  try {
    const l = await getJson('/debug/stt_level');
    if (!l) { el.innerHTML = '<div class="empty">還沒收到 STT 音量回報（STT 服務沒連上，或還沒收到任何音訊）</div>'; return; }
    const pct = Math.min(100, Math.round((l.rms || 0) / 0.3 * 100));
    const speaking = l.vad === 'speech';
    el.innerHTML = `
      <div style="background:#12141a; border-radius:6px; height:18px; overflow:hidden; margin-bottom:8px;">
        <div style="height:100%; width:${pct}%; background:${speaking ? '#22c55e' : '#374151'}; transition:width .2s;"></div>
      </div>
      <table>
        <tr><th>RMS 音量</th><td>${(l.rms ?? 0).toFixed(4)}</td></tr>
        <tr><th>峰值</th><td>${(l.peak ?? 0).toFixed(4)}</td></tr>
        <tr><th>VAD 狀態</th><td>${speaking ? '<b style="color:#86efac">speech（判定成在講話）</b>' : 'silence（沒偵測到講話）'}</td></tr>
        <tr><th>累計收到秒數</th><td>${l.audio_seconds ?? 0} 秒</td></tr>
      </table>`;
  } catch (e) {
    el.innerHTML = `<div class="empty">連線失敗：${esc(e.message)}</div>`;
  }
}

function summarize(entry) {
  const r = entry.response || {};
  if (entry.kind === 'screen_observation') return `text: ${r.text || ''}\\nerror: ${r.error || '(null)'}`;
  if (entry.kind === 'chat_reply') return `expr: ${r.expr || ''}\\ntext: ${r.text || ''}`;
  if (entry.kind === 'homework_analysis') {
    const rea = r.reassurance || {};
    let s = `analysis: ${(r.analysis || '').slice(0, 120)}\\nreassurance: [${rea.expr || ''}] ${rea.text || ''}\\nchatgpt_prompt: ${(r.chatgpt_prompt || '').slice(0, 120)}`;
    if ('chatgpt_sent' in r) s += `\\nChatGPT 送出: ${r.chatgpt_sent ? '成功' : '失敗 - ' + (r.chatgpt_error || '')}`;
    return s;
  }
  if (entry.kind === 'touch') return `kind: ${r.kind || ''}（強度 ${r.strength ?? ''}）`;
  if (entry.kind === 'stt_final') return `聽到: ${r.text || ''}\\n路由到: ${r.routed_to || ''}`;
  if (entry.kind === 'esp32_say') return `expr: ${(entry.request || {}).expr || ''}\\ntext: ${(entry.request || {}).text || ''}\\n送出: ${r.sent ? '成功' : '失敗 - ' + (r.error || '')}`;
  if (entry.kind === 'chatgpt_send') return `送出: ${r.sent ? '成功' : '失敗 - ' + (r.error || '')}\\nprompt: ${((entry.request || {}).prompt || '').slice(0, 120)}`;
  if (entry.kind === 'cam_snapshot') return r.ok ? '拍照成功' : `拍照失敗: ${r.error || ''}`;
  return JSON.stringify(r);
}

async function refreshFeed() {
  const el = document.getElementById('feed');
  try {
    const items = await getJson('/debug/trace?n=30');
    if (!items.length) { el.innerHTML = '<div class="empty">還沒有任何呼叫紀錄</div>'; return; }
    el.innerHTML = items.map(e => `
      <div class="entry">
        ${e.image_b64 ? `<img src="data:image/jpeg;base64,${e.image_b64}" />` : ''}
        <div class="entry-body">
          <div class="entry-head"><span class="kind ${e.kind}">${e.kind}</span><span>${esc(e.ts_iso)}</span></div>
          <div class="entry-summary">${esc(summarize(e))}</div>
          <details><summary>原始 request/response JSON</summary>
            <pre>${esc(JSON.stringify({request: e.request, response: e.response}, null, 2))}</pre>
          </details>
        </div>
      </div>`).join('');
  } catch (e) {
    el.innerHTML = `<div class="empty">連線失敗：${esc(e.message)}</div>`;
  }
}

async function refreshMemory() {
  const el = document.getElementById('memory');
  try {
    const rows = await getJson('/debug/memory/recent?n=15');
    if (!rows.length) { el.innerHTML = '<div class="empty">還沒有資料</div>'; return; }
    el.innerHTML = `<table><tr><th>時間</th><th>來源</th><th>內容</th><th>重要度</th></tr>` +
      rows.slice().reverse().map(m => `<tr><td>${esc(m.ts_end)}</td><td>${esc(m.source)}</td><td>${esc(m.text)}</td><td>${m.importance}</td></tr>`).join('') +
      `</table>`;
  } catch (e) {
    el.innerHTML = `<div class="empty">連線失敗：${esc(e.message)}</div>`;
  }
}

function setMsg(id, text, ok) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = 'msg ' + (ok ? 'ok' : 'err');
}

async function sendGesture() {
  const kind = document.getElementById('gestureKind').value;
  try {
    await getJson('/debug/gesture', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ kind, strength: 1.0, dur_ms: 200 }) });
    setMsg('msg-gesture', '已送出：' + kind, true);
    refreshFeed(); refreshMemory();
  } catch (e) { setMsg('msg-gesture', '失敗：' + e.message, false); }
}

async function sendExpr() {
  const expr = document.getElementById('exprKind').value;
  try {
    await getJson('/debug/expr', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ expr }) });
    setMsg('msg-expr', '已送出：' + expr, true);
    refreshFeed();
  } catch (e) { setMsg('msg-expr', '失敗：' + e.message, false); }
}

async function sendUtterance() {
  const text = document.getElementById('utteranceText').value.trim();
  if (!text) { setMsg('msg-utterance', '請先輸入文字', false); return; }
  try {
    await getJson('/debug/utterance', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ text }) });
    setMsg('msg-utterance', '已送出，等回覆跑完後看下面 trace', true);
    setTimeout(() => { refreshFeed(); refreshMemory(); }, 1500);
  } catch (e) { setMsg('msg-utterance', '失敗：' + e.message, false); }
}

async function sendScreenshot() {
  try {
    const r = await getJson('/debug/screenshot', { method: 'POST' });
    setMsg('msg-screenshot', '完成，前景：' + JSON.stringify(r.foreground || {}), true);
    refreshFeed(); refreshMemory();
  } catch (e) { setMsg('msg-screenshot', '失敗：' + e.message, false); }
}

async function seedMemory() {
  try {
    const r = await getJson('/debug/memory/seed', { method: 'POST' });
    setMsg('msg-memory-admin', `已植入 ${r.inserted.length} 筆假記憶`, true);
    refreshMemory();
  } catch (e) { setMsg('msg-memory-admin', '失敗：' + e.message, false); }
}

async function clearMemory() {
  if (!confirm('確定要清空所有記憶嗎？這個動作沒辦法復原。')) return;
  try {
    await getJson('/debug/memory/clear', { method: 'DELETE' });
    setMsg('msg-memory-admin', '已清空', true);
    refreshMemory();
  } catch (e) { setMsg('msg-memory-admin', '失敗：' + e.message, false); }
}

async function sendRetrieve() {
  const query = document.getElementById('retrieveQuery').value.trim();
  const el = document.getElementById('retrieveResult');
  if (!query) { setMsg('msg-retrieve', '請先輸入查詢文字', false); return; }
  try {
    const hits = await getJson('/debug/retrieve?query=' + encodeURIComponent(query));
    setMsg('msg-retrieve', `找到 ${hits.length} 筆`, true);
    if (!hits.length) { el.innerHTML = '<div class="empty">沒有符合的記憶（可能還沒植入任何資料）</div>'; return; }
    el.innerHTML = `<table><tr><th>排名</th><th>內容</th><th>來源</th><th>總分</th><th>vector</th><th>keyword</th><th>decay</th><th>重要度</th></tr>` +
      hits.map((h, i) => `<tr>
        <td>${i + 1}</td><td>${esc(h.memory_text)}</td><td>${esc(h.source)}</td>
        <td>${h.score.toFixed(3)}</td><td>${h.vector_score.toFixed(3)}</td>
        <td>${h.text_score.toFixed(3)}</td><td>${h.decay.toFixed(3)}</td><td>${h.importance}</td>
      </tr>`).join('') + `</table>`;
  } catch (e) { setMsg('msg-retrieve', '失敗：' + e.message, false); }
}

async function sendHomework() {
  const fileInput = document.getElementById('homeworkImage');
  if (!fileInput.files.length) { setMsg('msg-homework', '請先選一張圖片', false); return; }
  const form = new FormData();
  form.append('image', fileInput.files[0]);
  form.append('transcript', document.getElementById('homeworkTranscript').value);
  form.append('send_to_chatgpt', document.getElementById('homeworkSend').checked);
  try {
    const res = await fetch('/debug/homework', { method: 'POST', body: form });
    if (!res.ok) throw new Error(await res.text());
    const body = await res.json();
    let msg = '分析完成，結果見下面 trace';
    if ('chatgpt_sent' in body) msg += body.chatgpt_sent ? '；已送到 ChatGPT' : ('；送 ChatGPT 失敗：' + body.chatgpt_error);
    setMsg('msg-homework', msg, !('chatgpt_sent' in body) || body.chatgpt_sent);
    refreshFeed(); refreshMemory();
  } catch (e) { setMsg('msg-homework', '失敗：' + e.message, false); }
}

function tick() { refreshFeed(); refreshMemory(); }
tick();
setInterval(tick, 3000);

loadGestureConfig();
function fastTick() { refreshStatus(); refreshLcdState(); refreshTelemetry(); refreshSttLevel(); }
fastTick();
setInterval(fastTick, 300);
</script>
</body>
</html>
"""
