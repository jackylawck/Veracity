"""
International Military Tribunal (Nuremberg IMT) Production Adapter
符合 BaseAdapter 統一時間窗口，採集二戰終結紐倫堡大審判、戰犯公文證據與國際刑法原始卷宗。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.Nuremberg")

class NurembergImtIngestionError(Exception):
    pass

class NurembergImtProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_NUREMBERG"
    # 史丹佛虛擬法庭 / 紐倫堡審判檔案檢索 API
    API_URL = "https://virtualtribunals.stanford.edu/api/v1/records/search"
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
            return "Untitled Nuremberg Tribunal Evidence Dossier"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NUREMBERG] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NUREMBERG] Archive portal maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NurembergImtIngestionError(f"Nuremberg API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NurembergImtIngestionError("Nuremberg retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NUREMBERG] Applying Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "International Military Tribunal Nuremberg Trial Evidence War Crimes",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("exhibitId", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    fonds_name = doc.get("tribunal", "International Military Tribunal (IMT) at Nuremberg")
                    call_no = doc.get("documentNumber", f"IMT-EXHIBIT-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"nuremberg:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "International Military Tribunal Archives (Stanford / Peace Palace)",
                                "zh": "國際軍事法庭紐倫堡審判檔案庫 (史丹佛 / 和平宮)"
                            },
                            "fonds": fonds_name,
                            "series": "國際軍事法庭戰犯審判逐字紀錄與官方證物系列",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "IMT_Public_Historical_Domain",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official proceedings and exhibits of the International Military Tribunal. Public Domain worldwide.",
                                "zh": "國際軍事法庭官方審判紀錄與呈堂證物，屬全球公有領域歷史法證檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://virtualtribunals.stanford.edu/record/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NUREMBERG] Batch isolated failure: {e}")
                break

        logger.info(f"[NUREMBERG] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
