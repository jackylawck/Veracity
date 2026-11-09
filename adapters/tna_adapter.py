"""
The Veracity // UK The National Archives (TNA) Production Archival Adapter
主權檔案採集適配器：對齊認識論誠實、涵蓋年限過濾與零逃生門契約
"""
import logging
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Dict, List, Optional, Tuple
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
    認識論約定：
    1. sps.startDate / sps.endDate 過濾的是公文內容涵蓋年代 (coveringDates)，非官方解密開放日。
    2. 採集結果若為 0 筆則誠實回傳空列表，絕不注入任何合成/假資料 (Zero-Fallback)。
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

    def fetch_records(self, query: str = "war", max_records: int = 20) -> List[Dict[str, Any]]:
        """
        向 TNA Discovery API 請求已編目之解密歷史公文。
        若連線失敗或無資料，回傳空列表 []，維護 0 筆空總帳之認識論誠實。
        """
        start_date, end_date = self.get_date_window()
        params = {
            "sps.searchQuery": query,
            "sps.heldByFilter": "TNA",
            "sps.startDate": start_date,
            "sps.endDate": end_date,
            "sps.page": "0",
            "sps.resultsPageSize": str(min(max_records, 50))
        }

        retrieved_at = datetime.now(timezone.utc).isoformat()
        try:
            resp = self.session.get(DISCOVERY_API_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("TNA 端點查詢異常或超時，依零逃生門守則回傳空紀錄: %s", exc)
            return []

        raw_records = data.get("records") if isinstance(data, dict) else None
        if not isinstance(raw_records, list):
            return []

        normalized: List[Dict[str, Any]] = []
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            rec_id = item.get("id") or item.get("iaid")
            if not rec_id:
                continue

            record_payload: Dict[str, Any] = {
                "record_id": f"UK_TNA_{rec_id}",
                "title": item.get("title") or "Untitled Archival Record",
                "reference": item.get("cpc") or item.get("reference") or str(rec_id),
                "covering_dates": item.get("coveringDates") or f"{start_date} - {end_date}",
                "repository": self.NAME,
                "description": item.get("scopeContent") or item.get("description") or "",
                "source_url": f"https://discovery.nationalarchives.gov.uk/details/r/{rec_id}",
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
                    "raw_id": str(rec_id)
                },
                "heuristics": {
                    "status": "UNCOMPUTED_IN_SINGLE_PASS",
                    "flags": []
                }
            }
            normalized.append(record_payload)
            if len(normalized) >= max_records:
                break

        return normalized


__all__ = ["TnaProductionAdapter"]
