"""FSR1 雙擊觸發的拍照倒數頁面（見 docs/api.html §⑥、docs/HANDOFF_TODO.md 第 4 項）。
給「使用者」看的，不是給開發者看的 debug 工具，所以風格跟 dashboard_html.py
的技術面板不同——這裡要友善、大字、看得懂在幹嘛。

倒數本身完全是前端純計時（不等後端訊號），只要長度跟 main.py 的
`await asyncio.sleep(5)` 一致就好，見該檔案的說明；拍照/分析完成後靠輪詢
/debug/trace 抓最新的 homework_analysis、chatgpt_send 兩種紀錄來顯示結果。
"""

COUNTDOWN_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>拍照分析中</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0;
    background: radial-gradient(circle at 50% 30%, #1c2333 0%, #0b0e16 70%);
    color: #f2f0ea;
    font-family: -apple-system, "PingFang TC", "Noto Sans TC", sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100%;
    padding: 24px;
    text-align: center;
  }
  h1 { font-size: 16px; font-weight: 500; color: #9aa4c2; margin: 0 0 22px; letter-spacing: .04em; }

  .stage {
    position: relative;
    width: min(90vw, 480px);
    aspect-ratio: 4 / 3;
    border-radius: 18px;
    overflow: hidden;
    background: #05070c;
    border: 1px solid #2a3350;
    box-shadow: 0 20px 60px rgba(0,0,0,.5);
  }
  .stage img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .cam-fallback {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    color: #6b7595; font-size: 14px; padding: 20px; text-align: center;
  }
  .count-overlay {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    background: rgba(5,7,12,.28);
    backdrop-filter: blur(1px);
  }
  .count-num {
    font-size: 120px;
    font-weight: 700;
    text-shadow: 0 4px 30px rgba(0,0,0,.6);
    animation: pop .5s ease;
  }
  @keyframes pop { from { transform: scale(.6); opacity: 0; } to { transform: scale(1); opacity: 1; } }

  .status {
    margin-top: 26px;
    font-size: 17px;
    color: #d7dbea;
    max-width: 480px;
    min-height: 26px;
  }
  .spinner {
    display: inline-block; width: 14px; height: 14px; margin-right: 8px;
    border: 2px solid #4a5578; border-top-color: #d7dbea; border-radius: 50%;
    animation: spin .8s linear infinite; vertical-align: -2px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .result {
    margin-top: 18px;
    background: #171d2e;
    border: 1px solid #2a3350;
    border-radius: 14px;
    padding: 18px 22px;
    max-width: 480px;
    font-size: 18px;
    line-height: 1.6;
  }
  .result .sub { margin-top: 10px; font-size: 13px; color: #8b95b8; }
  .expr-tag {
    display: inline-block; font-size: 12px; padding: 2px 9px; border-radius: 999px;
    background: #2a3350; color: #b9c2e6; margin-bottom: 8px;
  }
</style>
</head>
<body>
  <h1>壓 FSR1 兩下 &middot; 作業拍照分析</h1>

  <div class="stage">
    <img id="camImg" src="__CAM_STREAM_URL__" alt="相機預覽"
         onerror="this.replaceWith(Object.assign(document.createElement('div'), {className:'cam-fallback', textContent:'找不到相機（ESP32-CAM 還沒接上也沒關係，倒數跟分析照樣進行）'}))" />
    <div class="count-overlay" id="overlay"><div class="count-num" id="num">5</div></div>
  </div>

  <div class="status" id="status"></div>
  <div id="resultBox"></div>

<script>
(function () {
  "use strict";
  var n = 5;
  var numEl = document.getElementById("num");
  var overlayEl = document.getElementById("overlay");
  var statusEl = document.getElementById("status");
  var resultBox = document.getElementById("resultBox");
  var startedAt = Date.now() / 1000 - 1; // 留一點餘裕，避免時間邊界剛好卡掉

  function esc(s) {
    return String(s).replace(/[&<>]/g, function (c) { return {"&":"&amp;","<":"&lt;",">":"&gt;"}[c]; });
  }

  function stopCameraPreview() {
    // The ESP32-CAM has one blocking HTTP client: release /cam/stream before
    // the backend asks for /cam/snapshot.
    var camImg = document.getElementById("camImg");
    camImg.removeAttribute("src");
    camImg.src = "about:blank";
  }

  function tick() {
    if (n > 0) {
      numEl.textContent = n;
      n -= 1;
      setTimeout(tick, 1000);
    } else {
      stopCameraPreview();
      overlayEl.style.display = "none";
      statusEl.innerHTML = '<span class="spinner"></span>拍照中，分析中...';
      pollForResult();
    }
  }

  var gotAnalysis = false, gotChatgpt = false, lastStageTs = 0;

  function updateStage(items) {
    var stage = items.find(function (it) {
      return it.kind === "homework_stage" && it.ts >= startedAt && it.ts > lastStageTs;
    });
    if (!stage) return;
    lastStageTs = stage.ts;
    var response = stage.response || {};
    if (response.stage === "complete" || response.stage === "failed") {
      statusEl.textContent = response.label || "流程結束";
    } else {
      statusEl.innerHTML = '<span class="spinner"></span>' + esc(response.label || "處理中…");
    }
  }

  function pollForResult() {
    var iv = setInterval(function () {
      fetch("/debug/trace?n=15").then(function (r) { return r.json(); }).then(function (items) {
        updateStage(items);
        if (!gotAnalysis) {
          var hit = items.find(function (it) { return it.kind === "homework_analysis" && it.ts >= startedAt; });
          if (hit) {
            gotAnalysis = true;
            var rea = (hit.response || {}).reassurance || {};
            statusEl.textContent = "分析完成";
            resultBox.innerHTML = '<div class="result">' +
              '<span class="expr-tag">' + esc(rea.expr || "neutral") + "</span><br/>" +
              esc(rea.text || "（沒有回覆內容）") +
              '<div class="sub" id="chatgptLine">正在確認 ChatGPT 送出狀態...</div>' +
              "</div>";
          }
        }
        if (gotAnalysis && !gotChatgpt) {
          var cg = items.find(function (it) { return it.kind === "chatgpt_send" && it.ts >= startedAt; });
          if (cg) {
            gotChatgpt = true;
            var line = document.getElementById("chatgptLine");
            if (line) {
              line.textContent = cg.response.sent
                ? "已經送到 ChatGPT 了"
                : "沒有送到 ChatGPT：" + (cg.response.error || "未知原因");
            }
          }
        }
        if (gotAnalysis && gotChatgpt) clearInterval(iv);
      }).catch(function () {});
    }, 1500);
    // 保險：超過 2 分鐘都沒結果就停止輪詢，並明確告知使用者。
    setTimeout(function () {
      clearInterval(iv);
      if (!gotAnalysis) statusEl.textContent = "分析逾時，請查看除錯頁面的 trace/log。";
    }, 120000);
  }

  tick();
})();
</script>
</body>
</html>
"""
