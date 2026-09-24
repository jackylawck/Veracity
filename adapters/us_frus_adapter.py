"""
US Department of State Office of the Historian (FRUS) Production Adapter
符合 BaseAdapter 統一時間窗口，採集美國對外關係 (Foreign Relations of the United States) 法定解密頂級外交總卷。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.FRUS")

class FrusIngestionError(Exception):
    pass

class FrusProductionAdapter(BaseAdapter):
    NAME = "US_FRUS"
    # 美國國務院歷史文獻處官方 REST API
    API_URL = "https://history.state.gov/api/v1/catalog/search"
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
            return "Untitled FRUS Declassified Diplomatic Volume"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[FRUS] Rate limit encountered (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[FRUS] Service endpoint temporarily offline ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise FrusIngestionError(f"FRUS API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise FrusIngestionError("FRUS retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[FRUS] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "China Soviet Crisis Foreign Relations",
                "start-year": start_year,
                "end-year": end_year,
                "page": str(page_idx + 1),
                "per-page": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                results = payload.get("results", []) or payload.get("items", [])

                if not results:
                    break

                for item in results:
                    volume_id = str(item.get("id") or item.get("volume-id", "")).strip()
                    if not volume_id or volume_id in seen_ids:
                        continue
                    seen_ids.add(volume_id)

                    clean_title = self.clean_text(item.get("title"))
                    coverage = item.get("coverage-dates", f"{start_year}-{end_year}")

                    record: Dict[str, Any] = {
                        "record_id": f"frus:{volume_id}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "US Department of State Office of the Historian (Washington, D.C.)",
                                "zh": "美國國務院歷史文獻處 (華盛頓特區)"
                            },
                            "fonds": "Foreign Relations of the United States (FRUS)",
                            "series": "Official Declassified Diplomatic History Series",
                            "call_number": f"FRUS-{volume_id}",
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": coverage
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "US_Public_Domain",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official documentary record of US foreign policy under 22 U.S.C. 4351. Public Domain worldwide.",
                                "zh": "依美國聯邦法典第 22 卷第 4351 條法定解密並公佈之官方文獻，屬公有領域史料。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://history.state.gov/historicaldocuments/{volume_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[FRUS] Batch processing error: {e}")
                break

        logger.info(f"[FRUS] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
