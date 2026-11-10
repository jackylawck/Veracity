/* ==========================================================================
   The Veracity // Forensic Console Easter Egg & Epistemic Attestation
   Deterministic Matrix CRT Terminal (Zero-Ghost-Files / Epistemic Fit)
   ========================================================================== */
(function () {
  const asciiBanner = String.raw`
┌────────────────────────────────────────────────────────────────────────┐
│  01001111 01010000 01000101 01001110 00100000 01010011 01001111 01010101 │
│  ﾘ ｸ ｺ ｳ ｼ ﾊ ﾐ ﾋ ｰ ｳ ｼ ﾅ ﾓ ﾆ ｻ ﾜ ﾂ ｵ ﾘ ｱ ﾎ ﾃ ﾏ ｹ ﾒ ｴ ｶ ｷ ﾑ ﾕ ﾗ ｾ ﾈ ｽ ﾀ │
│                                                                        │
│   _______ _            __      __                  _ _                 │
│  |__   __| |           \ \    / /                 (_) |                │
│     | |  | |__   ___    \ \  / /__ _ __ __ _  ___ _ _| |_ _   _        │
│     | |  | '_ \ / _ \    \ \/ / _ \ '__/ _` |/ __| | | __| | | |       │
│     | |  | | | |  __/     \  /  __/ | | (_| | (__| | | |_| |_| |       │
│     |_|  |_| |_|\___|      \/ \___|_|  \__,_|\___|_|_|\__|\__, |       │
│                                                            __/ |       │
│                                                           |___/        │
│   [ SOVEREIGN DECLASSIFICATION LEDGER // DETERMINISTIC NON-AI ]       │
└────────────────────────────────────────────────────────────────────────┘`;

  const fontStack = "font-family: 'Courier New', 'MS Gothic', 'Osaka-Mono', monospace;";

  const phosphorGreen = `color: #00ff66; ${fontStack} font-size: 11px; font-weight: bold; line-height: 1.25; text-shadow: 0 0 7px rgba(0,255,102,0.8);`;
  const terminalAmber = `color: #ffb454; ${fontStack} font-size: 11px; font-weight: bold; line-height: 1.5;`;
  const epistemicGreen = `color: #3fb950; ${fontStack} font-size: 11px; line-height: 1.5;`;
  const auditBlue      = `color: #58a6ff; ${fontStack} font-size: 10px; line-height: 1.4;`;

  console.log("%c" + asciiBanner, phosphorGreen);

  console.log(
    "%c> WAKE UP, AUDITOR...\n" +
    "> THE MATRIX IS NARRATIVE. THE VERACITY IS FIXITY.\n" +
    "> FOLLOW THE CRYPTOGRAPHIC EVIDENCE.\n",
    terminalAmber
  );

  console.log(
    "%c[EPISTEMOLOGICAL BOUNDARY / 認識論邊界憲章]\n" +
    "• Layer 1: 密碼學存證只擔保數位位元流真實完整，不對歷史內容作實質真偽裁斷。\n" +
    "• Layer 2: 涵蓋年限過濾（Covering Dates 1945~Current-30）約束形成期，非解密開放日。\n" +
    "• Layer 3: 恪守零逃生門（Zero-Fallback），空總帳 (N=0) 亦屬合法之真實狀態。\n" +
    "• Layer 4: 演算法不裁決歷史，歷史解釋權永遠歸屬學者、專家與公民社會。",
    epistemicGreen
  );

  console.log(
    "\n%c🔐 FIXITY: SHA-256 Merkle Roots | SIGSTORE: Keyless Transparency Log\n" +
    "AUDIT ENGINE: https://github.com/jackylawck/Veracity",
    auditBlue
  );
})();
