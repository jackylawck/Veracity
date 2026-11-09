"""
The Veracity // Archival Heuristics Engine
史料批判與全宗斷層線索標註器：僅輸出探索建議，嚴格標示演算法局限性。
（恪守認識論邊界：啟發式線索僅供研究者延伸查核，不具備密碼學存證效力）
"""
from types import MappingProxyType
from typing import Dict, Any, List

HEURISTICS_SPEC_VERSION = "1.1.0"

# 物理層級唯讀映射：防止進程生命週期內遭下游意外賦值竄改
EPISTEMOLOGICAL_DISCLAIMER = MappingProxyType({
    "en": "Algorithmic heuristic clues indicate potential custodial gaps or anomalies for scholarly exploration. They do not constitute historical rulings or definitive proof of archival withholding.",
    "zh": "演算法線索僅標示潛在移交斷層或全宗異常以供學者探索，絕不代表歷史判決或官方隱匿之終局證明。"
})


class ArchivalHeuristicsEngine:
    @staticmethod
    def _extract_repository_label(record: Dict[str, Any]) -> Dict[str, str]:
        """動態提取典藏機構標籤，避免硬編碼單一檔案館名稱"""
        ctx = record.get("archival_context") or {}
        repo = ctx.get("repository")
        
        if isinstance(repo, dict):
            return {
                "en": repo.get("en") or "relevant national archive",
                "zh": repo.get("zh") or "相關主權檔案館"
            }
        elif isinstance(repo, str) and repo.strip():
            return {"en": repo.strip(), "zh": repo.strip()}
        
        return {"en": "sovereign archival repository", "zh": "主權典藏機關"}

    @classmethod
    def inspect_lacunae(cls, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        掃描全宗與案卷斷層線索（單卷目錄標註待查狀態）。
        採防禦性淺拷貝與引用隔離，杜絕物件就地竄改與常量污染。

        邊界聲明：對 raw_clues 採用 dict() 淺拷貝；當前實現僅追加全新獨立鍵
        custodial_gap_indicator，不改動既有結構。若未來需原地改動深層嵌套欄位，
        應審慎切換至 copy.deepcopy。
        """
        if not isinstance(records, list):
            return []

        annotated: List[Dict[str, Any]] = []

        for r in records:
            if not isinstance(r, dict):
                continue

            # 建立防禦性複製，維護函數純粹性與冪等性
            item = dict(r)
            raw_clues = item.get("heuristic_clues")
            clues: Dict[str, Any] = dict(raw_clues) if isinstance(raw_clues, dict) else {}

            repo_label = cls._extract_repository_label(item)

            clues["custodial_gap_indicator"] = {
                "engine_version": HEURISTICS_SPEC_VERSION,
                "heuristic_status": "UNCOMPUTED_IN_SINGLE_PASS",
                "gap_suspected": None,
                "scholarly_action_required": {
                    "en": f"Requires global fonds sequence traversal. Consult {repo_label['en']} series inventory manually.",
                    "zh": f"單卷目錄無法自動推導序列斷層。請人工查閱 {repo_label['zh']} 系列清冊以確認移交狀態。"
                },
                # 注入獨立字典實例，阻斷下游改寫傳導
                "epistemological_disclaimer": dict(EPISTEMOLOGICAL_DISCLAIMER)
            }

            item["heuristic_clues"] = clues
            annotated.append(item)

        return annotated

    @classmethod
    def annotate_lacunae_status(cls, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        語意化別名：標註單卷全宗斷層待查狀態。
        透過 cls.inspect_lacunae 動態分派，嚴格維持 Python MRO 繼承多型支援。
        """
        return cls.inspect_lacunae(records)
