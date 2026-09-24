"""
Bank for International Settlements (BIS Archives, Basel) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後中央銀行秘密黃金轉移、馬歇爾計劃清算與 G10 行長會議解密原卷。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.BIS")

class BisArchivesIngestionError(Exception):
    pass

class BankInternationalSettlementsProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_BIS"
    # 國際清算銀行公開歷史檔案目錄檢索 REST API
    API_URL = "https://www.bis.org/api/v1/archives/search"
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
            return "Untitled BIS Central Banking Archival Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[BIS] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[BIS] Archives gateway maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise BisArchivesIngestionError(f"BIS API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise BisArchivesIngestionError("BIS retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[BIS] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Central Bank Gold Settlements Marshall Plan G10 Declassified",
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
                    ref_code = str(doc.get("referenceCode") or doc.get("id", "")).strip()
                    if not ref_code or ref_code in seen_ids:
                        continue
                    seen_ids.add(ref_code)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    fonds_name = doc.get("fonds", "Bank for International Settlements Central Archives (BISA)")
                    call_no = doc.get("referenceCode", f"BISA-{ref_code}")

                    record: Dict[str, Any] = {
                        "record_id": f"bis:{ref_code.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Bank for International Settlements Archives (Basel, Switzerland)",
                                "zh": "國際清算銀行檔案館 (瑞士巴塞爾)"
                            },
                            "fonds": fonds_name,
                            "series": "央行理事會秘密會議、黃金儲備清算與冷戰貨幣互換系列",
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
                            "license_category": "BIS_Open_Archive_Rules",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Historical records disclosed under the BIS Rules on Public Access to the BIS Archives (30-year rule).",
                                "zh": "依國際清算銀行《公眾查閱檔案規則》（30年法定解密原則）開放之國際金融檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.bis.org/about/arch_rules/dossier/{ref_code}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[BIS] Batch isolated failure: {e}")
                break

        logger.info(f"[BIS] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
