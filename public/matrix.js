/* ==========================================================================
   The Veracity // Forensic Console Easter Egg & Epistemic Attestation
   ========================================================================== */
(function () {
  const banner = `
%c  _______ _            __      __                  _ _         
 |__   __| |           \\ \\    / /                 (_) |        
    | |  | |__   ___    \\ \\  / /__ _ __ __ _  ___ _ _| |_ _   _ 
    | |  | '_ \\ / _ \\    \\ \\/ / _ \\ '__/ _\` |/ __| | | __| | | |
    | |  | | | |  __/     \\  /  __/ | | (_| | (__| | | |_| |_| |
    |_|  |_| |_|\\___|      \\/ \\___|_|  \\__,_|\\___|_|_|\\__|\\__, |
                                                            __/ |
  揭古 // Sovereign Historical Ledger                      |___/ 
  Deterministic Bitstream Provenance Engine // Non-AI
`;

  console.log(banner, "color: #58a6ff; font-weight: bold; font-family: monospace;");

  console.log(
    "%c⚖️ [EPISTEMOLOGICAL BOUNDARY / 認識論邊界憲章]\n" +
    "%c• Layer 1 密碼學存證只擔保公文元數據位元流之真實完整，絕不對歷史內容作實質真偽裁斷。\n" +
    "• 涵蓋年限過濾器（Covering Dates Horizon: 1945 ~ Current-30）約束公文形成年代，非解密釋出日。\n" +
    "• 系統恪守零偽資料逃生門（Zero-Fallback），空總帳 (N=0) 亦屬合法之真實狀態。\n" +
    "• 歷史解釋權永遠歸屬獨立學者、法證專家與公民社會。",
    "color: #e3b341; font-weight: bold; font-size: 13px;",
    "color: #8b949e; font-size: 11px; line-height: 1.6;"
  );

  console.log(
    "%c🔐 [CRYPTOGRAPHIC FIXITY]\n" +
    "%cAll dossiers anchored via SHA-256 fixity trees and Sigstore keyless attestation.\n" +
    "Audit Ledger Repo: https://github.com/jackylawck/Veracity",
    "color: #3fb950; font-weight: bold; font-size: 12px;",
    "color: #8b949e; font-size: 11px;"
  );
})();
