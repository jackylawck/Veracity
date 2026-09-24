"""
National Archives Department of Myanmar (NAD, Naypyidaw) Production Adapter
符合 BaseAdapter 統一時間窗口，採集中緬印戰區 (CBI)、龐隆協議 (Panglong Agreement) 與戰後非殖民建政檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NAD")

class NadArchivesIngestionError(Exception):
    pass

class MyanmarNadProductionAdapter(BaseAdapter):
    NAME = "ASIA_NAD"
    # 緬甸國家檔案局公開檢索端點 (National Archives Digital Catalog)
    API_URL = "https://nationalarchives.gov.mm/api/v1/records/search"
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
            return "Untitled Myanmar National Archival Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NAD] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NAD] Archives portal maintenance ({resp.status_code}).")
                    return {"records": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NadArchivesIngestionError(f"NAD API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NadArchivesIngestionError("NAD retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 1947 年龐隆協議，1948 年緬甸正式獨立
        nad_start = max(1947, int(start_year))
        logger.info(f"[NAD] Applying Historical Window: {nad_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Panglong Agreement CBI Theater Decolonization Post-War Independence",
                "startYear": str(nad_start),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("records", []) or payload.get("data", [])

                if not records:
                    break

                for doc in records:
                    record_id = str(doc.get("id") or doc.get("accessionNo", "")).strip()
                    if not record_id or record_id in seen_ids:
                        continue
                    seen_ids.add(record_id)

                    title_my = self.clean_text(doc.get("title") or doc.get("description"))
                    call_no = doc.get("accessionNo", f"NAD-MM-{record_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"mmnad:{record_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives Department of Myanmar (Naypyidaw & Yangon)",
                                "zh": "緬甸國家檔案局 (奈比多與仰光)"
                            },
                            "fonds": "Post-Independence Government Secretariat Fonds",
                            "series": "龐隆建國協議、中緬印戰區接收與對外邊界條約系列",
                            "call_number": call_no,
                            "title": {
                                "en": f"[National Archives of Myanmar] {title_my}",
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{nad_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Myanmar_National_Records_and_Archives_Law",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Historical records disclosed under the National Records and Archives Law of Myanmar.",
                                "zh": "依緬甸《國家紀錄與檔案法》法定解密開放之公共歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://nationalarchives.gov.mm/record/{record_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NAD] Batch isolated failure: {e}")
                break

        logger.info(f"[NAD] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
