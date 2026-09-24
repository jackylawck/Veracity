"""
Swiss Federal Archives (Schweizerisches Bundesarchiv - BAR) Production Adapter
符合 BaseAdapter 統一時間窗口，採集永久中立國第三方秘密外交與聯邦檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.BAR")

class SwissBarIngestionError(Exception):
    pass

class SwissBarProductionAdapter(BaseAdapter):
    NAME = "SWISS_BAR"
    # 瑞士聯邦公開檔案檢索 API (opendata.swiss / BAR 通用端點)
    API_URL = "https://www.bar.admin.ch/api/v1/records/search"
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
            return "Schweizerisches Bundesarchiv Dossier (Untitled)"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[SWISS_BAR] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[SWISS_BAR] API service gateway maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise SwissBarIngestionError(f"Swiss BAR API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise SwissBarIngestionError("Swiss BAR retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[SWISS_BAR] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Guerre froide neutralite diplomatie",
                "fromYear": start_year,
                "toYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("dossiers", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("archiveSignature", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    signature = doc.get("archiveSignature", f"E2001-{doc_id}")
                    fonds = doc.get("fonds", "E2001 (Eidgenössisches Politisches Departement)")
                    title_orig = self.clean_text(doc.get("title") or doc.get("description"))

                    record: Dict[str, Any] = {
                        "record_id": f"swissbar:{doc_id.replace(' ', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Swiss Federal Archives (Bern)",
                                "zh": "瑞士聯邦檔案館 (伯恩)"
                            },
                            "fonds": fonds,
                            "series": doc.get("series", "Auswärtige Angelegenheiten (Foreign Affairs)"),
                            "call_number": signature,
                            "title": {
                                "en": title_orig,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateRange", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Swiss_Public_Sector_Information",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Open government data governed by Federal Act on Archiving (BGA).",
                                "zh": "依瑞士《聯邦檔案法》（BGA）解密開放之公共資訊，供自由學術研究。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.recherche.bar.admin.ch/recherche/#/en/archive/einheit/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[SWISS_BAR] Batch isolated failure: {e}")
                break

        logger.info(f"[SWISS_BAR] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
