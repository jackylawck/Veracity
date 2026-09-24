"""
Legislative Council Archives of Hong Kong (LegCo Archives) Production Adapter
符合 BaseAdapter 統一時間窗口，採集香港戰後立法局會議紀錄、法案辯論及憲制過渡歷史公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.LegCo")

class LegcoArchivesIngestionError(Exception):
    pass

class LegcoArchivesProductionAdapter(BaseAdapter):
    NAME = "HK_LEGCO"
    # 香港立法會公開資料 API (LegCo Open Data API)
    API_URL = "https://app4.legco.gov.hk/odata/LegcoOpenData.svc/Hansard"
    USER_AGENT = "VeracityLedger/2.0 (Historical Forensics Engine; Solo-Maintainer Verification)"

    def __init__(self, timeout: int = 15, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json"
        })

    @staticmethod
    def clean_text(raw_text: Optional[str]) -> str:
        if not raw_text:
            return "未命名立法局會議紀錄 (Official LegCo Hansard Record)"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[LEGCO] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[LEGCO] LegCo OData service offline ({resp.status_code}).")
                    return {"value": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise LegcoArchivesIngestionError(f"LegCo Archives API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise LegcoArchivesIngestionError("LegCo Archives retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[LEGCO] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            # OData 標準查詢過濾
            params = {
                "$filter": f"MeetingYear ge {start_year} and MeetingYear le {end_year}",
                "$top": str(page_size),
                "$skip": str(page_idx * page_size),
                "$orderby": "MeetingDate asc"
            }

            try:
                payload = self._execute_with_retry(params)
                items = payload.get("value", [])

                if not items:
                    break

                for item in items:
                    meeting_id = str(item.get("MeetingID") or item.get("RecordID", "")).strip()
                    if not meeting_id or meeting_id in seen_ids:
                        continue
                    seen_ids.add(meeting_id)

                    en_title = self.clean_text(item.get("SubjectEng") or item.get("MeetingDate"))
                    zh_title = self.clean_text(item.get("SubjectChi")) if item.get("SubjectChi") else None
                    meeting_date = item.get("MeetingDate", f"{start_year}-{end_year}")

                    record: Dict[str, Any] = {
                        "record_id": f"legco:{meeting_id}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Legislative Council Archives of Hong Kong (Admiralty)",
                                "zh": "香港立法會檔案處 (金鐘立法會綜合大樓)"
                            },
                            "fonds": "Legislative Council Historical Hansard Fonds",
                            "series": "戰後立法局官方會議紀錄 (Hansard Series)",
                            "call_number": f"LEGCO-HANSARD-{meeting_id}",
                            "title": {
                                "en": f"[LegCo Hansard] {en_title}",
                                "zh": zh_title
                            },
                            "covering_dates": meeting_date[:10] if len(meeting_date) >= 10 else meeting_date
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "LegCo_Open_Data_Terms",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official proceedings of the Legislative Council under LegCo Open Data Terms and Conditions.",
                                "zh": "依香港立法會開放資料條款公開之議事會議紀錄。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.legco.gov.hk/hansard/record/{meeting_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[LEGCO] Batch isolated failure: {e}")
                break

        logger.info(f"[LEGCO] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
