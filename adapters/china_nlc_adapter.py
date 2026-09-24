"""
National Library of China (NLC Special Collections, Beijing) Production Adapter
符合 BaseAdapter 统一时间窗口，采集近现代革命历史文献、官方公报孤本与战后建国初期文献档案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NLC")

class NlcArchivesIngestionError(Exception):
    pass

class ChinaNlcProductionAdapter(BaseAdapter):
    NAME = "CN_NLC"
    # 中国国家图书馆特藏文献与近代史料检索 REST API
    API_URL = "http://read.nlc.cn/api/v1/modern-history/search"
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
            return "未命名国家图书馆近代历史文献"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NLC] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NLC] Catalog service offline ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NlcArchivesIngestionError(f"NLC API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NlcArchivesIngestionError("NLC retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NLC] Applying Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "战后 接收 协商会议 建设 外部条约",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("data", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("recordId") or doc.get("callNo", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    title_cn = self.clean_text(doc.get("title") or doc.get("name"))
                    collection_name = doc.get("collection", "国家图书馆近现代革命与政务特藏全宗")
                    call_no = doc.get("callNo", f"NLC-DOC-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"cnnlc:{doc_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Library of China Special Collections (Beijing)",
                                "zh": "中國國家圖書館特藏資源部 (北京海淀)"
                            },
                            "fonds": collection_name,
                            "series": "近現代政務公告、歷史公報孤本與政府條約系列",
                            "call_number": call_no,
                            "title": {
                                "en": f"[National Library of China] {title_cn}",
                                "zh": title_cn
                            },
                            "covering_dates": doc.get("publishDate", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "China_National_Cultural_Heritage_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Open digital historical documentation catalog provided by the National Library of China for scholarly research.",
                                "zh": "依中國國家典籍資源開放政策提供之近現代歷史文獻目錄，供學術研究查閱。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"http://read.nlc.cn/allSearch/searchDetail?searchType=all&showType=1&indexName=data_513&id={doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NLC] Batch isolated failure: {e}")
                break

        logger.info(f"[NLC] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
