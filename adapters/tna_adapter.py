"""
The Veracity // UK The National Archives (TNA) Production Archival Adapter
主權檔案採集適配器：對齊認識論誠實、HTML清洗、重試防禦與分頁死循環保護
"""
import html
import logging
import re
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Dict, List, Optional, Set, Tuple
import requests

try:
    from adapters.base_adapter import BaseAdapter
except ImportError:
    class BaseAdapter:  # type: ignore[no-redef]
        """Fallback BaseAdapter interface if base module is decoupled."""
        NAME: str = "BASE"

logger = logging.getLogger(__name__)

DISCOVERY_API_URL = "https://discovery.nationalarchives.gov.uk/API/search/records"
USER_AGENT = "TheVeracity/2.1 (Forensic Declassification Ledger; +https://jackylawck.github.io/Veracity/)"
REQUEST_HEADERS = MappingProxyType({
    "User-Agent": USER_AGENT,
    "Accept": "application/json"
})


class TnaProductionAdapter(BaseAdapter):
    """
    英國國家檔案館 (TNA Kew) 官方 Discovery API 採集管線。
    """
    NAME: str = "UK_TNA"
    REPOSITORY_NAME: str = "The National Archives, Kew (UK)"
    START_YEAR: int = 1945

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(dict(REQUEST_HEADERS))

    @property
    def end_year(self) -> int:
        """動態計算維護者設計之歷史涵蓋截止線 (Current Year - 30)"""
        return datetime.now(timezone.utc).year - 30

    def get_date_window(self) -> Tuple[str, str]:
        """回傳 (startDate, endDate) 字串格式 YYYY-MM-DD"""
        return f"{self.START_YEAR}-01-01", f"{self.end_year}-12-31"

    @staticmethod
    def clean_html_markup(raw: Optional[str]) -> str:
        """
        過濾 TNA API 回傳欄位中的 HTML 標籤並反轉義 HTML 實體字元。
        """
        if not raw:
            return ""
        text = re.sub(r"<[^>]+>", "", str(raw))
        text = html.unescape(text)
        return " ".join(text.split())

    def _execute_with_retry(self, params: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """封裝帶重試之 HTTP 請求，供管線防禦與單元測試 mock 攔截"""
        for attempt in range(max_retries):
            try:
                resp = self.session.get(DISCOVERY_API_URL, params=params, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    return data
                return {}
            except Exception as exc:
                if attempt == max_retries - 1:
                    logger.warning("TNA 端點查詢異常或重試耗盡: %s", exc)
                    return {}
        return {}

    def fetch_records(
        self,
        query: str = "war",
        max_records: int = 20,
        max_pages: int = 10,
        **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """
        向 TNA Discovery API 請求歷史公文，支援自動分頁與重複批次死循環偵測。
        若連線失敗或無資料，回傳空列表 []，維護 0 筆空總帳之認識論誠實。
        """
        start_date, end_date = self.get_date_window()
        page = 0
        page_size = min(max_records, 50)
        seen_ids: Set[str] = set()
        normalized: List[Dict[str, Any]] = []
        retrieved_at = datetime.now(timezone.utc).isoformat()

        while len(normalized) < max_records and page < max_pages:
            params = {
                "sps.searchQuery": query,
                "sps.heldByFilter": "TNA",
                "sps.startDate": start_date,
                "sps.endDate": end_date,
                "sps.page": str(page),
                "sps.resultsPageSize": str(page_size)
            }

            data = self._execute_with_retry(params)
            raw_records = data.get("records") if isinstance(data, dict) else None
            if not isinstance(raw_records, list) or not raw_records:
                break

            batch_new = 0
            for item in raw_records:
                if not isinstance(item, dict):
                    continue
                rec_id = item.get("id") or item.get("iaid")
                if not rec_id:
                    continue
                str_id = str(rec_id)
                if str_id in seen_ids:
                    continue
                seen_ids.add(str_id)
                batch_new += 1

                raw_title = item.get("title") or "Untitled Archival Record"
                raw_desc = item.get("scopeContent") or item.get("description") or ""

                record_payload: Dict[str, Any] = {
                    "record_id": f"UK_TNA_{str_id}",
                    "title": self.clean_html_markup(raw_title),
                    "reference": item.get("cpc") or item.get("reference") or str_id,
                    "covering_dates": item.get("coveringDates") or f"{start_date} - {end_date}",
                    "repository": self.NAME,
                    "description": self.clean_html_markup(raw_desc),
                    "source_url": f"https://discovery.nationalarchives.gov.uk/details/r/{str_id}",
                    "verification_level": "metadata_only",
                    "fixity": {
                        "algorithm": "SHA-256",
                        "hash_value": None
                    },
                    "provenance": {
                        "source": self.NAME,
                        "repository_name": self.REPOSITORY_NAME,
                        "retrieved_at_utc": retrieved_at,
                        "temporal_filter_semantic": "covering_dates_not_release_date",
                        "covering_dates_horizon": f"{self.START_YEAR}-{self.end_year}",
                        "raw_id": str_id
                    },
                    "heuristics": {
                        "status": "UNCOMPUTED_IN_SINGLE_PASS",
                        "flags": []
                    }
                }
                normalized.append(record_payload)
                if len(normalized) >= max_records:
                    break

            # 分頁死循環防禦：若整批資料均已出現過，立即終止爬取
            if batch_new == 0:
                logger.info("分頁檢測到重複資料批次，觸發迴圈阻斷保護。")
                break

            page += 1

        return normalized


__all__ = ["TnaProductionAdapter"]