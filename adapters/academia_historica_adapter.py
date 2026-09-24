"""
Academia Historica (Taiwan) Production Adapter
符合 BaseAdapter 統一時間窗口，採集大溪檔案、國民政府軍政移交與中華民國歷任總統府機密史料。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.Historica")

class HistoricaIngestionError(Exception):
    pass

class AcademiaHistoricaProductionAdapter(BaseAdapter):
    NAME = "TW_HISTORICA"
    # 國史館史料檔案檢索系統開放 API
    API_URL = "https://ahonline.drnh.gov.tw/api/v1/archives/search"
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
            return "未命名國史館國家重要機密檔案"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[TW_HISTORICA] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[TW_HISTORICA] System catalog maintenance ({resp.status_code}).")
                    return {"records": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise HistoricaIngestionError(f"Academia Historica API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise HistoricaIngestionError("Academia Historica retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[TW_HISTORICA] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "keyword": "總統府 軍事 接管 美援 台海防衛",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                items = payload.get("records", []) or payload.get("data", [])

                if not items:
                    break

                for doc in items:
                    doc_id = str(doc.get("id") or doc.get("archiveNo", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    zh_title = self.clean_text(doc.get("title") or doc.get("subject"))
                    fonds_name = doc.get("fondsName", "蔣中正總統檔案 (大溪檔案全宗)")
                    call_no = doc.get("archiveNo", f"AH-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"twhistorica:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Academia Historica (Taipei & Xindian)",
                                "zh": "國史館 (臺北館與新店檔案大樓)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("seriesName", "總統府大溪檔案與國家重要施政系列"),
                            "call_number": call_no,
                            "title": {
                                "en": f"[Academia Historica] {zh_title}",
                                "zh": zh_title
                            },
                            "covering_dates": doc.get("dateDisplay", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Academia_Historica_Open_Data",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified primary records released under the Archives Act and Presidential Records Act.",
                                "zh": "依《國家機密保護法》、《檔案法》及《總統副總統文物管理條例》法定解密開放之國家檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://ahonline.drnh.gov.tw/index.php?act=Display/image/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[TW_HISTORICA] Batch isolated failure: {e}")
                break

        logger.info(f"[TW_HISTORICA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
