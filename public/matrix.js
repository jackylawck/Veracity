/* ==========================================================================
   The Veracity // Forensic Console Easter Egg & Epistemic Attestation
   Deterministic Matrix CRT Terminal (58-col Compact / Interactive Getters)
   ========================================================================== */
(function () {
  // 1. 防止打包與壓縮工具誤刪日誌，鎖定原生列印通道
  const log = console.log.bind(console);

  const asciiBanner = String.raw`
┌────────────────────────────────────────────────────────┐
│ 01001111 01010000 01000101 01001110 01010011 01001111  │
│ ﾘ ｸ ｺ ｳ ｼ ﾊ ﾐ ﾋ ｰ ｳ ｼ ﾅ ﾓ ﾆ ｻ ﾜ ﾂ ｵ ﾘ ｱ ﾎ ﾃ ﾏ ｹ ﾒ ｴ ｶ  │
│                                                        │
│  _______ _             __      __                 _    │
│ |__   __| |            \ \    / /                (_)   │
│    | |  | |__   ___     \ \  / /__ _ __ __ _  ___ _    │
│    | |  | '_ \ / _ \     \ \/ / _ \ '__/ _' |/ __| |   │
│    | |  | | | |  __/      \  /  __/ | | (_| | (__| |   │
│    |_|  |_| |_|\___|       \/ \___|_|  \__,_|\___|_|   │
│                                                        │
│  SOVEREIGN PROVENANCE LEDGER // DETERMINISTIC NON-AI   │
└────────────────────────────────────────────────────────┘`;

  const fontStack = "font-family: 'Courier New', 'MS Gothic', 'Osaka-Mono', monospace;";

  const phosphorGreen  = `color: #00ff66; background: #020502; ${fontStack} font-size: 11px; font-weight: bold; line-height: 1.25; text-shadow: 0 0 5px rgba(0,255,102,0.6);`;
  const terminalAmber  = `color: #ffb454; ${fontStack} font-size: 11px; font-weight: bold; line-height: 1.5;`;
  const epistemicGreen = `color: #2ea043; ${fontStack} font-size: 11px; line-height: 1.5;`;
  const auditBlue      = `color: #0969da; ${fontStack} font-size: 10px; line-height: 1.4;`;
  const cmdBadge       = `color: #020502; background: #00ff66; ${fontStack} font-size: 10px; font-weight: bold; padding: 1px 4px;`;

  function printAxioms() {
    log(
      "%c[EPISTEMOLOGICAL BOUNDARY / 認識論邊界憲章]\n" +
      "• Layer 1: 密碼學存證只擔保數位位元流真實完整，不對歷史內容作實質真偽裁斷。\n" +
      "• Layer 2: 涵蓋年限過濾（Covering Dates 1945~Current-30）約束形成期，非解密開放日。\n" +
      "• Layer 3: 恪守零逃生門（Zero-Fallback），空總帳 (N=0) 亦屬合法之真實狀態。\n" +
      "• Layer 4: 演算法不裁決歷史，歷史解釋權永遠歸屬學者、專家與公民社會。",
      epistemicGreen
    );
  }

  // 2. 防呆與記憶體清理機制：0.8 秒 CRT 解密脈衝特效
  let glitchTimer = null;
  function triggerDeclassifyPulse() {
    const root = document.documentElement;
    const styleId = "veracity-crt-pulse-style";

    // 若連續輸入指令，先清理舊定時器
    if (glitchTimer) {
      clearTimeout(glitchTimer);
      glitchTimer = null;
    }

    // 注入臨時動畫樣式（若尚未存在）
    let styleEl = document.getElementById(styleId);
    if (!styleEl) {
      styleEl = document.createElement("style");
      styleEl.id = styleId;
      styleEl.textContent = `
        @keyframes veracity-glitch {
          0%   { filter: hue-rotate(0deg) contrast(100%); transform: translate(0, 0); }
          20%  { filter: hue-rotate(90deg) contrast(140%) brightness(1.1); transform: translate(-2px, 1px); }
          40%  { filter: invert(0.08) hue-rotate(135deg) contrast(160%); transform: translate(2px, -1px); }
          60%  { filter: hue-rotate(110deg) saturate(200%); transform: translate(-1px, 0); }
          80%  { filter: hue-rotate(45deg) contrast(120%); transform: translate(1px, 1px); }
          100% { filter: none; transform: translate(0, 0); }
        }
        .veracity-glitch-active {
          animation: veracity-glitch 0.8s cubic-bezier(0.25, 0.46, 0.45, 0.94) both;
        }
      `;
      document.head.appendChild(styleEl);
    }

    // 重置 class 並透過 void offsetWidth 強制瀏覽器重繪，確保連點也能重新觸發動畫
    root.classList.remove("veracity-glitch-active");
    void root.offsetWidth;
    root.classList.add("veracity-glitch-active");

    // 0.8 秒後徹底移除 class 與 style 節點，零 DOM 殘留、零記憶體洩漏
    glitchTimer = setTimeout(() => {
      root.classList.remove("veracity-glitch-active");
      const targetStyle = document.getElementById(styleId);
      if (targetStyle) {
        targetStyle.remove();
      }
      glitchTimer = null;
    }, 800);
  }

  // 3. 註冊免括號指令（支援大小寫直接輸入 Enter 觸發）
  function registerCommand(name, handler) {
    [name.toUpperCase(), name.toLowerCase()].forEach((key) => {
      if (!(key in window)) {
        Object.defineProperty(window, key, {
          configurable: true,
          enumerable: false,
          get: function () {
            handler();
            return `[EXEC: ${name.toUpperCase()}]`;
          }
        });
      }
    });
  }

  registerCommand("VERACITY", () => {
    const records = Array.isArray(window.__VERACITY_RECORDS__) ? window.__VERACITY_RECORDS__ : [];
    const health = window.__VERACITY_HEALTH__ || {};
    log(
      "%c[AUDIT TELEMETRY / 即時記憶體總帳快照]\n" +
      `• In-Memory Dossiers : ${records.length} records\n` +
      `• Circuit Breaker    : ${health.status || "ACTIVE (±2.5σ)"}\n` +
      `• Verification Mode  : Client-Side WebCrypto SHA-256 (Zero-Server-Trust)`,
      terminalAmber
    );
  });

  registerCommand("AXIOMS", () => {
    printAxioms();
  });

  registerCommand("RED_PILL", () => {
    log("%c> DECRYPTING SURFACE LAYER... SEEING RAW BITSTREAM.", phosphorGreen);
    triggerDeclassifyPulse();
  });

  // 初始啟動列印
  log("%c" + asciiBanner, phosphorGreen);

  log(
    "%c> WAKE UP, AUDITOR...\n" +
    "> THE MATRIX IS NARRATIVE. THE VERACITY IS FIXITY.\n" +
    "> FOLLOW THE CRYPTOGRAPHIC EVIDENCE.\n",
    terminalAmber
  );

  printAxioms();

  log(
    "\n%c🔐 FIXITY: SHA-256 Merkle Roots | SIGSTORE: Keyless Transparency Log\n" +
    "AUDIT ENGINE: https://github.com/jackylawck/Veracity",
    auditBlue
  );

  log(
    "\n%c[INTERACTIVE CONSOLE COMMANDS - TYPE WITHOUT PARENS]\n" +
    "%c VERACITY %c Inspect live ledger telemetry   " +
    "%c AXIOMS %c Review epistemic boundary   " +
    "%c RED_PILL %c Trigger CRT pulse",
    terminalAmber,
    cmdBadge, auditBlue,
    cmdBadge, auditBlue,
    cmdBadge, auditBlue
  );
})();
