"""
World Meteorological Organization (WMO Archives, Geneva) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後核試驗放射性大氣擴散監測、全球天氣監視網與跨國地球物理觀測原卷。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.WMO")

class WmoArchivesIngestionError(Exception):
    pass

class WorldMeteorologicalOrganizationProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_WMO"
    # 世界氣象組織圖書與歷史文獻開放檢索 REST API
    API_URL = "https://library.wmo.int/api/v1/records/search"
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
            return "Untitled WMO Atmospheric Observation Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[WMO] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[WMO] Library portal under maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise WmoArchivesIngestionError(f"WMO API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise WmoArchivesIngestionError("WMO retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # WMO 於 1950 年正式成立
        wmo_start = max(1950, int(start_year))
        logger.info(f"[WMO] Applying Historical Window: {wmo_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Atmospheric Radioactivity Nuclear Fallout World Weather Watch Observation",
                "startYear": str(wmo_start),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("items", [])

                if not records:
                    break

                for doc in records:
                    pub_id = str(doc.get("publicationNo") or doc.get("id", "")).strip()
                    if not pub_id or pub_id in seen_ids:
                        continue
                    seen_ids.add(pub_id)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    constituent = doc.get("body", "Commission for Atmospheric Sciences / Executive Council")
                    call_no = doc.get("publicationNo", f"WMO-PUB-{pub_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"wmo:{pub_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "World Meteorological Organization Archives (Geneva, Switzerland)",
                                "zh": "世界氣象組織歷史檔案處 (瑞士日內瓦)"
                            },
                            "fonds": f"WMO Executive Council & Technical Commissions Fonds ({constituent})",
                            "series": "全球核試驗放射性大氣擴散監測、地球物理觀測與氣象主權資料系列",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{wmo_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "WMO_Public_Access_Policy",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Scientific and technical historical documentation released under WMO General Regulations on Information Access.",
                                "zh": "依世界氣象組織資訊查閱總章程公開之科學與技術歷史公文。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://library.wmo.int/records/{pub_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[WMO] Batch isolated failure: {e}")
                break

        logger.info(f"[WMO] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
