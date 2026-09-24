"""
Vera and Donald Blinken Open Society Archives (OSA) Production Adapter
符合 BaseAdapter 統一時間窗口，採集蘇聯東歐地下出版物 (Samizdat)、自由歐洲電台與冷戰人權解密文獻。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.BlinkenOSA")

class BlinkenOsaIngestionError(Exception):
    pass

class BlinkenOsaProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_OSA"
    # Blinken OSA 公開目錄檢索 REST API
    API_URL = "https://catalog.osaarchivum.org/api/v1/records/search"
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
            return "Untitled Samizdat / Cold War Archival Dossier"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[BlinkenOSA] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[BlinkenOSA] Catalog portal maintenance ({resp.status_code}).")
                    return {"data": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise BlinkenOsaIngestionError(f"Blinken OSA API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise BlinkenOsaIngestionError("Blinken OSA retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[BlinkenOSA] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Samizdat Radio Free Europe Dissident Human Rights Cold War",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("data", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    item_id = str(doc.get("id") or doc.get("reference_code", "")).strip()
                    if not item_id or item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    clean_title = self.clean_text(doc.get("title"))
                    fonds_name = doc.get("fonds_title", "HU OSA 300 (Records of Radio Free Europe/Radio Liberty)")
                    call_no = doc.get("reference_code", f"OSA-{item_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"osa:{item_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Vera and Donald Blinken Open Society Archives (Budapest)",
                                "zh": "布林肯開放社會檔案館 (布達佩斯)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("series_title", "Cold War Research Institute & Samizdat Archives"),
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("date_display", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "OSA_Open_Access_Commons",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Primary sources preserved for open society research under Blinken OSA Access Guidelines.",
                                "zh": "由布林肯開放社會檔案館保存，依開放社會研究指南提供歷史檢驗。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://catalog.osaarchivum.org/catalog/{item_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[BlinkenOSA] Batch isolated failure: {e}")
                break

        logger.info(f"[BlinkenOSA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
