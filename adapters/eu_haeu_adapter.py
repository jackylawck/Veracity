"""
Historical Archives of the European Union (HAEU / EUI Florence) Production Adapter
符合 BaseAdapter 統一時間窗口，採集歐洲煤鋼共同體 (ECSC)、歐洲經濟共同體 (EEC) 及冷戰西歐超國家整合公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.HAEU")

class HaeuArchivesIngestionError(Exception):
    pass

class HaeuArchivesProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_HAEU"
    # 歐盟歷史檔案館公開 OAI-PMH / REST 檢索端點
    API_URL = "https://archives.eui.eu/api/v1/records/search"
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
            return "Untitled European Community Archival Dossier"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[HAEU] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[HAEU] Gateway portal maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise HaeuArchivesIngestionError(f"HAEU API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise HaeuArchivesIngestionError("HAEU retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 歐洲煤鋼共同體成立於 1952 年
        eu_start = max(1952, int(start_year))
        logger.info(f"[HAEU] Applying Historical Window: {eu_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "European Community Integration Treaties Council Commission",
                "startYear": str(eu_start),
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
                    doc_id = str(doc.get("id") or doc.get("referenceCode", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title"))
                    institution = doc.get("creator", "European Commission / Council of Ministers")
                    call_no = doc.get("referenceCode", f"HAEU-DOC-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"haeu:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Historical Archives of the European Union, EUI (Florence, Italy)",
                                "zh": "歐洲聯盟歷史檔案館 / 歐洲大學學院 (義大利佛羅倫斯)"
                            },
                            "fonds": f"Fonds {institution}",
                            "series": doc.get("series", "European Integration & Common Foreign Policy Series"),
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{eu_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "EU_Council_Regulation_354_83",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified records of the European Communities open under Council Regulation (EEC, Euratom) No 354/83 (30-year rule).",
                                "zh": "依歐洲共同體理事會第 354/83 號條例（30年解密法則）開放之歐盟官方歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://archives.eui.eu/en/fonds/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[HAEU] Batch isolated failure: {e}")
                break

        logger.info(f"[HAEU] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
