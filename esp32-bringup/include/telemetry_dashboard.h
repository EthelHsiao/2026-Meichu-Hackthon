#pragma once

static const char TELEMETRY_DASHBOARD[] PROGMEM = R"HTML(<!doctype html>
<html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>ESP32 感測器測試</title>
<style>
body{font:16px system-ui;max-width:850px;margin:32px auto;padding:0 20px;background:#f5f7fa;color:#192d40}
section{background:white;border:1px solid #d8e1e8;border-radius:12px;padding:18px;margin:16px 0}
button,a{margin-right:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}
progress{width:100%;height:22px}small{color:#526577}
</style>
<h1>ESP32 感測器測試</h1>
<p id="status">正在連線…</p>
<p><a href="/api/v1/health">HTTP 狀態</a><a href="/api/v1/telemetry">HTTP 最新一筆</a>
<button id="ping" disabled>測試雙向 ping</button><span id="pong"></span></p>
<section><h2>壓感器 · raw ADC</h2><p id="fsr">等待資料</p>
<progress id="f1" max="4095" value="0"></progress><progress id="f2" max="4095" value="0"></progress>
<small>0–4095 是 ADC 讀值，尚未換算成力。未接線時請停用 FSR。</small></section>
<section><h2>MPU6050 · 六軸</h2><pre id="imu">等待資料</pre></section>
<section><h2>最新封包</h2><pre id="packet"></pre></section>
<script>
const el=id=>document.getElementById(id);let socket,lastReceived=0,received=0;
function connect(){
  socket=new WebSocket(`ws://${location.hostname}:__WS_PORT__/api/v1/stream`);
  socket.onopen=()=>{el('status').textContent='已連線，等待感測資料';el('ping').disabled=false;};
  socket.onmessage=e=>{
    let p;try{p=JSON.parse(e.data);}catch{el('status').textContent='收到無效 JSON';return;}
    if(p.type==='pong'){el('pong').textContent='收到 pong，雙向通道成功';return;}
    if(p.type!=='telemetry')return;
    lastReceived=Date.now();received++;
    el('status').textContent=`串流中 · 收到 ${received} 筆 · seq ${p.seq} · 開機 ${p.uptime_ms} ms`;
    el('fsr').textContent=p.fsr.enabled?`FSR1: ${p.fsr.raw[0]} / FSR2: ${p.fsr.raw[1]}`:'FSR 已停用';
    el('f1').value=p.fsr.raw?.[0]??0;el('f2').value=p.fsr.raw?.[1]??0;
    el('imu').textContent=p.imu.ok?`加速度 (m/s²): ${p.imu.accel_m_s2.join(', ')}\n角速度 (rad/s): ${p.imu.gyro_rad_s.join(', ')}\n溫度 (°C): ${p.imu.temperature_c}`:`IMU: ${p.imu.status}`;
    el('packet').textContent=JSON.stringify(p,null,2);
  };
  socket.onerror=()=>socket.close();
  socket.onclose=()=>{el('status').textContent='已斷線，2 秒後重連…';el('ping').disabled=true;setTimeout(connect,2000);};
}
el('ping').onclick=()=>{el('pong').textContent='等待 pong…';socket.send('ping');};
setInterval(()=>{if(socket?.readyState===1&&lastReceived&&Date.now()-lastReceived>3000)el('status').textContent='超過 3 秒未收到資料';},1000);
connect();
</script></html>)HTML";
