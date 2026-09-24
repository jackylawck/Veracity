"""
Nationaal Archief (National Archives of the Netherlands) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後歐洲北約盟國、海牙國際條約與海外解密公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NetherlandsNA")

class NetherlandsNaIngestionError(Exception):
    pass

class NetherlandsNaProductionAdapter(BaseAdapter):
    NAME = "NL_NA"
    # 荷蘭國家檔案館公開開放數據檢索端點
    API_URL = "https://opendata.nationaalarchief.nl/v1/records"
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
            return "Untitled Nationaal Archief Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NL_NA] Rate limit encountered (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NL_NA] Gateway maintenance window ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NetherlandsNaIngestionError(f"Netherlands NA API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NetherlandsNaIngestionError("Netherlands NA retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NL_NA] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Koude Oorlog Buitenlandse Zaken declassified",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("items", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("identifier", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    fonds_name = doc.get("archiveName", "Ministerie van Buitenlandse Zaken (2.05)")
                    call_no = doc.get("inventoryNumber", f"NL-HaNA-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"nlna:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Nationaal Archief of the Netherlands (The Hague)",
                                "zh": "荷蘭國家檔案館 (海牙)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("series", "Post-War Foreign Policy & Decolonisation Archives"),
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("period", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "CC0_1_0_Public_Domain",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Open metadata released by Nationaal Archief under CC0 1.0 Universal Public Domain.",
                                "zh": "依荷蘭國家檔案館政策與 CC0 1.0 公有領域宣告開放之政府解密目錄。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.nationaalarchief.nl/onderzoeken/archief/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NL_NA] Batch isolated failure: {e}")
                break

        logger.info(f"[NL_NA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
