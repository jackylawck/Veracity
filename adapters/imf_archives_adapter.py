"""
International Monetary Fund (IMF Archives) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後布雷頓森林體系、主權債務危機、執董會解密會議與金融援助原卷。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.IMF")

class ImfArchivesIngestionError(Exception):
    pass

class InternationalMonetaryFundProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_IMF"
    # 國際貨幣基金組織公開檔案檢索 REST API
    API_URL = "https://archivescatalog.imf.org/api/v1/records/search"
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
            return "Untitled IMF Executive Board Archival Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[IMF] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[IMF] Portal gateway maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise ImfArchivesIngestionError(f"IMF API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise ImfArchivesIngestionError("IMF retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[IMF] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Executive Board Monetary Policy Sovereign Debt Bretton Woods",
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
                    doc_id = str(doc.get("id") or doc.get("referenceCode", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    fonds_name = doc.get("fonds", "Executive Board of the International Monetary Fund")
                    call_no = doc.get("referenceCode", f"IMF-EBM-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"imf:{doc_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "International Monetary Fund Archives (Washington, D.C.)",
                                "zh": "國際貨幣基金組織歷史檔案處 (華盛頓特區)"
                            },
                            "fonds": fonds_name,
                            "series": "執董會秘密會議紀錄、成員國主權貸款與匯率監控系列",
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
                            "license_category": "IMF_Open_Archives_Policy",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified executive records disclosed under the IMF Policy on Access to Archives (20-year general declassification).",
                                "zh": "依國際貨幣基金組織《檔案開放政策》（20年法定解密原則）開放之國際金融檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://archivescatalog.imf.org/record/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[IMF] Batch isolated failure: {e}")
                break

        logger.info(f"[IMF] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
