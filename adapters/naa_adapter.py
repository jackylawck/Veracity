"""
National Archives of Australia (NAA) Production Adapter
符合 BaseAdapter 統一時間窗口，採集澳洲主權解密公文與亞太情報檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NAA")

class NaaIngestionError(Exception):
    pass

class NaaProductionAdapter(BaseAdapter):
    NAME = "AU_NAA"
    # 澳洲國家檔案館 RecordSearch 公開 REST 檢索端點
    API_URL = "https://recordsearch.naa.gov.au/SearchRetrieve/api/records/search"
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
            return "Untitled Commonwealth Archival Item"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NAA] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if not resp.ok:
                    logger.error(f"[NAA] API Error {resp.status_code}: {resp.text}")
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NaaIngestionError(f"NAA API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NaaIngestionError("NAA retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_barcodes: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NAA] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "kw": "Security Intelligence Cold War declassified",
                "startYear": start_year,
                "endYear": end_year,
                "accessStatus": "OPEN",
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                items = payload.get("items", []) or payload.get("results", [])

                if not items:
                    logger.info(f"[NAA] Stream exhausted at page {page_idx + 1}.")
                    break

                for item in items:
                    barcode = str(item.get("barcode") or item.get("id", "")).strip()
                    if not barcode or barcode in seen_barcodes:
                        continue
                    seen_barcodes.add(barcode)

                    clean_title = self.clean_text(item.get("title"))
                    series_num = item.get("seriesNumber", "A1838")
                    control_sym = item.get("controlSymbol", barcode)

                    record: Dict[str, Any] = {
                        "record_id": f"naa:{barcode}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives of Australia (Canberra)",
                                "zh": "澳洲國家檔案館 (坎培拉總館)"
                            },
                            "fonds": f"Series {series_num}",
                            "series": series_num,
                            "call_number": f"{series_num}/{control_sym}",
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": item.get("contentsDateRange", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Australian_Crown_Copyright_CC_BY_3_AU",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Commonwealth of Australia open archival material. Governed by Archives Act 1983.",
                                "zh": "依澳洲《1983年檔案法》（Archives Act 1983）法定解密之聯邦歷史公文。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://recordsearch.naa.gov.au/SearchRetrieve/Interface/DetailsReports/ItemDetail.aspx?Barcode={barcode}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NAA] Page {page_idx + 1} processing failed: {e}")
                break

        logger.info(f"[NAA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
