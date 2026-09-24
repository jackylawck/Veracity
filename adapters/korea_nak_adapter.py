"""
National Archives of Korea (NAK) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後大韓民國中央行政、外交與冷戰停戰公文檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NAK")

class NakIngestionError(Exception):
    pass

class KoreaNakProductionAdapter(BaseAdapter):
    NAME = "KR_NAK"
    # 韓國國家記錄院公開 OpenData API 端點
    API_URL = "https://www.archives.go.kr/api/records/search.do"
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
            return "대한민국 국가기록원 미명명 문서 (Untitled Archival Item)"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NAK] Throttled (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NAK] Korea NAK gateway offline ({resp.status_code}).")
                    return {"items": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NakIngestionError(f"Korea NAK API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NakIngestionError("Korea NAK retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NAK] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "searchWord": "외교 안보 냉전 조약",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "rows": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("items", []) or payload.get("data", [])

                if not records:
                    break

                for doc in records:
                    record_id = str(doc.get("recordId") or doc.get("docNo", "")).strip()
                    if not record_id or record_id in seen_ids:
                        continue
                    seen_ids.add(record_id)

                    title_kr = self.clean_text(doc.get("recordTitle") or doc.get("title"))
                    dept = doc.get("produceAgency", "외교부 / 국방부")
                    call_no = doc.get("docNo", f"NAK-{record_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"nak:{record_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives of Korea (Seongnam)",
                                "zh": "韓國國家記錄院 (城南國家記錄書庫)"
                            },
                            "fonds": dept,
                            "series": doc.get("recordType", "대통령기록물 및 중앙행정기관 공문서"),
                            "call_number": call_no,
                            "title": {
                                "en": f"[{dept}] {title_kr}",
                                "zh": title_kr
                            },
                            "covering_dates": doc.get("productionYear", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Korea_Open_Government_License_Type1",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Public records disclosed under Public Records Management Act and KOGL Type 1.",
                                "zh": "依《公共記錄物管理法》及韓國開放政府授權第 1 類（KOGL Type 1）公開之國家檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.archives.go.kr/next/search/listSubjectDescription.do?id={record_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NAK] Batch isolated failure: {e}")
                break

        logger.info(f"[NAK] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
