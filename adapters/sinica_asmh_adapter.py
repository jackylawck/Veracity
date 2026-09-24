"""
Academia Sinica Institute of Modern History (ASMH) Archives Production Adapter
符合 BaseAdapter 統一時間窗口，採集中央研究院近代史研究所中國近現代外交與戰後接收公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.SinicaASMH")

class SinicaAsmhIngestionError(Exception):
    pass

class SinicaAsmhProductionAdapter(BaseAdapter):
    NAME = "TW_ASMH"
    # 中研院近史所檔案館開放檢索端點 (Open Records API)
    API_URL = "https://archives.mh.sinica.edu.tw/api/v1/records/search"
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
            return "未命名近史所典藏檔案公文"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[ASMH] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[ASMH] Catalog maintenance ({resp.status_code}).")
                    return {"data": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise SinicaAsmhIngestionError(f"Sinica ASMH API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise SinicaAsmhIngestionError("Sinica ASMH retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[ASMH] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "kw": "戰後 條約 接管 外交部檔案 冷戰",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("data", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    archive_id = str(doc.get("archiveId") or doc.get("fileNo", "")).strip()
                    if not archive_id or archive_id in seen_ids:
                        continue
                    seen_ids.add(archive_id)

                    zh_title = self.clean_text(doc.get("title"))
                    fonds_name = doc.get("fondsName", "外交部檔案全宗 (02-01)")
                    call_no = doc.get("callNo", f"ASMH-{archive_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"asmh:{archive_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Institute of Modern History Archives, Academia Sinica (Taipei)",
                                "zh": "中央研究院近代史研究所檔案館 (南港)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("seriesName", "近代條約協定與戰後對外關係檔案"),
                            "call_number": call_no,
                            "title": {
                                "en": f"[Academia Sinica] {zh_title}",
                                "zh": zh_title
                            },
                            "covering_dates": doc.get("dateDisplay", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Academia_Sinica_Open_Data",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Academic open research catalog provided by Academia Sinica for historical forensics.",
                                "zh": "中央研究院近代史研究所開放目錄，依學術研究開放授權供公眾法證校驗。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://archives.mh.sinica.edu.tw/search/detail.aspx?id={archive_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[ASMH] Batch execution isolated failure: {e}")
                break

        logger.info(f"[ASMH] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
