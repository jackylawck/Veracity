"""
National Security Agency (NSA Declassified Central Archives) Production Adapter
符合 BaseAdapter 統一時間窗口，採集美國國家安全局 (NSA) 信號情報、維諾納計劃 (Venona) 與冷戰密碼破譯原檔。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NSA")

class NsaDeclassifiedIngestionError(Exception):
    pass

class NsaDeclassifiedProductionAdapter(BaseAdapter):
    NAME = "US_NSA_SIGINT"
    # 美國國家安全局官方解密公文檢索 API 端點
    API_URL = "https://www.nsa.gov/api/v1/declassified-records/search"
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
            return "Untitled NSA Declassified SIGINT Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NSA] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NSA] Archive service maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NsaDeclassifiedIngestionError(f"NSA API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NsaDeclassifiedIngestionError("NSA retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # NSA 成立於 1952 年（杜魯門秘密備忘錄）
        nsa_start = max(1952, int(start_year))
        logger.info(f"[NSA] Applying Historical Window: {nsa_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "keywords": "Venona Cryptanalysis Signals Intelligence Soviet Cold War",
                "start_year": str(nsa_start),
                "end_year": str(end_year),
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("accessionId", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title"))
                    call_no = doc.get("documentNumber", f"NSA-SIGINT-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"nsasigint:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Security Agency Central Archives (Fort Meade, Maryland)",
                                "zh": "美國國家安全局中央檔案館 (馬里蘭州米德堡)"
                            },
                            "fonds": "NSA / Central Security Service Declassified Cryptologic Fonds",
                            "series": "冷戰密碼分析、截獲電報破譯與信號情報 (SIGINT) 系列",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{nsa_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "US_Public_Domain_NSA_Declassified",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified cryptologic records released by the NSA Center for Cryptologic History.",
                                "zh": "由美國國家安全局密碼史中心依第 13526 號行政命令法定解密之歷史情報公文。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.nsa.gov/Helpful-Links/NSA-FOIA/Declassification-Transparency-Initiatives/Historical-Releases/Viewing-Page/Article/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NSA] Batch isolated failure: {e}")
                break

        logger.info(f"[NSA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
