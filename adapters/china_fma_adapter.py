"""
Ministry of Foreign Affairs of the PRC (FMA) Open Archives Adapter
符合 BaseAdapter 統一時間窗口，採集新中國早期解密外交檔案與公報目錄。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ChinaFMA")

class ChinaFmaIngestionError(Exception):
    pass

class ChinaFmaProductionAdapter(BaseAdapter):
    NAME = "CN_FMA"
    # 中國外交部開放檔案檢索通道 (Open Archival Portal REST API)
    API_URL = "https://dag.fmprc.gov.cn/api/v1/records/open-catalogs"
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
            return "未命名外交解密公文 (Untitled Diplomatic Record)"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[CN_FMA] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[CN_FMA] Portal under maintenance or access throttled ({resp.status_code}).")
                    return {"data": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise ChinaFmaIngestionError(f"China FMA API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise ChinaFmaIngestionError("China FMA retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 中國外交部解密公文主要自 1949 年建國檔案開始
        search_start = max(1949, int(start_year))
        logger.info(f"[CN_FMA] Applying Historical Window: {search_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "keyword": "双边会谈 和平共处 冷战解密",
                "startYear": str(search_start),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                items = payload.get("data", []) or payload.get("records", [])

                if not items:
                    break

                for doc in items:
                    file_no = str(doc.get("archive_no") or doc.get("id", "")).strip()
                    if not file_no or file_no in seen_ids:
                        continue
                    seen_ids.add(file_no)

                    zh_title = self.clean_text(doc.get("title") or doc.get("subject"))
                    fonds_no = doc.get("fonds_no", "101 (外交部檔案全宗)")

                    record: Dict[str, Any] = {
                        "record_id": f"cnfma:{file_no.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Ministry of Foreign Affairs Archives of the PRC (Beijing)",
                                "zh": "中華人民共和國外交部檔案館 (北京)"
                            },
                            "fonds": fonds_no,
                            "series": doc.get("category", "外交業務與條約全宗"),
                            "call_number": file_no,
                            "title": {
                                "en": f"[PRC MFA] {zh_title}",
                                "zh": zh_title
                            },
                            "covering_dates": doc.get("formation_date", f"{search_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "PRC_State_Archives_Open_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Officially declassified archival metadata released under PRC Archives Law.",
                                "zh": "依《中華人民共和國檔案法》向社會開放之解密公文檔案目錄。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://dag.fmprc.gov.cn/details?id={file_no}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[CN_FMA] Isolated batch failure: {e}")
                break

        logger.info(f"[CN_FMA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
