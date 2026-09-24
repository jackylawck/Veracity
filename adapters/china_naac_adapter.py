"""
National Archives Administration of China (NAAC / 中央档案馆) Production Adapter
符合 BaseAdapter 统一时间窗口，采集抗战胜利接收、国共和谈公文、中央政府历史解密档案目录。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NAAC")

class NaacArchivesIngestionError(Exception):
    pass

class ChinaNaacProductionAdapter(BaseAdapter):
    NAME = "CN_NAAC"
    # 全国档案查询利用服务平台 / 国家档案局开放目录 REST API
    API_URL = "https://services.saac.gov.cn/api/v1/records/search"
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
            return "未命名中央国家档案公文"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NAAC] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NAAC] Portal service maintenance ({resp.status_code}).")
                    return {"data": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NaacArchivesIngestionError(f"NAAC API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NaacArchivesIngestionError("NAAC retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NAAC] Applying Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "kw": "抗战胜利 接收 和谈 协定 建设 档案",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("data", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("recordId") or doc.get("archiveCode", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    title_cn = self.clean_text(doc.get("title") or doc.get("recordName"))
                    fonds_name = doc.get("fondsName", "中央国家机关及政务院历史档案全宗")
                    call_no = doc.get("archiveCode", f"NAAC-ARCH-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"cnnaac:{doc_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives Administration of China / Central Archives (Beijing)",
                                "zh": "國家檔案局 / 中央檔案館 (北京)"
                            },
                            "fonds": fonds_name,
                            "series": "戰後政權交接、重大施政綱領與國家建構法定檔案系列",
                            "call_number": call_no,
                            "title": {
                                "en": f"[Central Archives of China] {title_cn}",
                                "zh": title_cn
                            },
                            "covering_dates": doc.get("formDate", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "China_Archives_Law_Public_Disclosure",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified state records disclosed under the Archives Law of the People's Republic of China (25-year general declassification).",
                                "zh": "依《中華人民共和國檔案法》法定解密開放之國家歷史檔案（25年法定解密期限）。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://services.saac.gov.cn/record/detail/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NAAC] Batch isolated failure: {e}")
                break

        logger.info(f"[NAAC] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
