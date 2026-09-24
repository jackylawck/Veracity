"""
National Archives Administration, Taiwan (NEAR System) Production Adapter
符合 BaseAdapter 統一時間窗口，採集國家發展委員會檔案管理局國家檔案資訊網公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.TaiwanNEAR")

class TaiwanNearIngestionError(Exception):
    pass

class TaiwanNearProductionAdapter(BaseAdapter):
    NAME = "TW_NAA"
    # 國家檔案資訊網 (NEAR) 官方 OpenAPI 檢索端點
    API_URL = "https://near.archives.gov.tw/api/v1/search/records"
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
            return "未命名國家解密公文檔案"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[TW_NAA] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[TW_NAA] NEAR gateway offline ({resp.status_code}).")
                    return {"result": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise TaiwanNearIngestionError(f"Taiwan NEAR API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise TaiwanNearIngestionError("Taiwan NEAR retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[TW_NAA] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "冷戰 外交 條約 政治解密",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                items = payload.get("result", []) or payload.get("records", [])

                if not items:
                    break

                for doc in items:
                    doc_id = str(doc.get("archiveId") or doc.get("fileNo", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    zh_title = self.clean_text(doc.get("title") or doc.get("dossierTitle"))
                    agency = doc.get("producingAgency", "外交部")
                    file_no = doc.get("fileNo", doc_id)

                    record: Dict[str, Any] = {
                        "record_id": f"twnaa:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives Administration (New Taipei City)",
                                "zh": "國家發展委員會檔案管理局 (新莊)"
                            },
                            "fonds": agency,
                            "series": doc.get("seriesTitle", "重要外交與國防檔案全宗"),
                            "call_number": file_no,
                            "title": {
                                "en": f"[{agency}] {zh_title}",
                                "zh": zh_title
                            },
                            "covering_dates": doc.get("contentDateRange", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Taiwan_Open_Government_Data_License",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Open government archival metadata under Archives Act and Open Data License v1.0.",
                                "zh": "依《檔案法》及政府資料開放授權條款（OGDL-Taiwan-1.0）公開之國家公文檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://near.archives.gov.tw/search/dossier/detail?id={doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[TW_NAA] Batch query isolated failure: {e}")
                break

        logger.info(f"[TW_NAA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
