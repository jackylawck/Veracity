"""
World Bank Group (WBG) Archives Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後布雷頓森林體系、國家經濟援助及基礎建設解密評估報告。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.WBG")

class WbgArchivesIngestionError(Exception):
    pass

class WorldBankWbgProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_WBG"
    # 聯合國世界銀行歷史檔案開放 REST API
    API_URL = "https://archivesholdings.worldbank.org/api/v1/records/search"
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
            return "Untitled World Bank Group Archival Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[WBG] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[WBG] Archives gateway offline ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise WbgArchivesIngestionError(f"WBG API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise WbgArchivesIngestionError("WBG retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[WBG] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Reconstruction Development Loan Treaty Infrastructure",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("referenceCode", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title"))
                    fonds_name = doc.get("fonds", "International Bank for Reconstruction and Development (IBRD)")
                    call_no = doc.get("referenceCode", f"WBG-ARCH-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"wbg:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "World Bank Group Archives (Washington, D.C.)",
                                "zh": "世界銀行集團檔案館 (華盛頓特區)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("series", "Country Economic & Sector Work (CESW) Declassified Series"),
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
                            "license_category": "WBG_Access_to_Information_Policy",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified under the World Bank Policy on Access to Information.",
                                "zh": "依世界銀行《資訊獲取政策》（20年解密原則）開放之國家經濟評估與貸款解密檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://archivesholdings.worldbank.org/record/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[WBG] Batch isolated failure: {e}")
                break

        logger.info(f"[WBG] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
