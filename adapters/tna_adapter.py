cat << 'EOF' > adapters/tna_adapter.py
"""
The Veracity // UK The National Archives (TNA) Production Adapter
採用官方端點 /API/search/records，依據歷史公文涵蓋期（Covering Dates）過濾。
（恪守認識論誠實原則：本適配器過濾的是檔案「形成與涵蓋年限」，非檔案館「實體解密日期」）
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.TNA")


class AdapterIngestionError(Exception):
    """主權適配器採集致命異常，用於向上通知沙盒隔離引擎"""
    pass


class TnaProductionAdapter(BaseAdapter):
    NAME = "UK_TNA"
    PRIMARY_API_URL = "https://discovery.nationalarchives.gov.uk/API/search/records"
    FALLBACK_API_URL = "https://discovery.nationalarchives.gov.uk/API/records/v1/collection/search"
    USER_AGENT = "TheVeracity/2.1 (Sovereign Historical Forensics Ledger; +https://jackylawck.github.io/Veracity/)"

    def __init__(self, timeout: int = 15, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json"
        })

    @staticmethod
    def clean_html_markup(raw_text: Optional[str]) -> str:
        if not raw_text:
            return "Untitled Classified Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        cleaned = " ".join(unescaped.split()).strip()
        return cleaned or "Untitled Classified Document"

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        urls = [self.PRIMARY_API_URL, self.FALLBACK_API_URL]
        last_error = None

        for url in urls:
            for attempt in range(1, self.max_retries + 1):
                try:
                    resp = self.session.get(url, params=params, timeout=self.timeout)
                    
                    if resp.status_code == 429:
                        backoff = 2 ** attempt
                        logger.warning(f"[TNA] Rate Limited (429) on {url}. Retrying in {backoff}s...")
                        time.sleep(backoff)
                        continue
                        
                    if resp.status_code == 404:
                        logger.warning(f"[TNA] Endpoint {url} returned 404. Skipping retries.")
                        last_error = f"HTTP 404 on {url}"
                        break

                    resp.raise_for_status()
                    return resp.json()

                except requests.RequestException as exc:
                    last_error = str(exc)
                    if attempt == self.max_retries:
                        logger.warning(f"[TNA] Endpoint {url} exhausted retries: {exc}")
                        break
                    time.sleep(2 ** attempt)

        raise AdapterIngestionError(f"TNA API unreachable across all endpoints: {last_error}")

    def fetch_records(self, max_pages: int = 6, page_size: int = 25) -> List[Dict[str, Any]]:
        """
        採集 TNA 官方檔案：
        - 依系統年份計算 30 年涵蓋期截止線（current_year - 30）
        - 採用 0-based 分頁規範
        - title.zh 保留空字串 "" 以符合 Schema 並觸發前端官方原題提示
        """
        if max_pages <= 0:
            raise ValueError(f"max_pages must be positive, got {max_pages}")
        if page_size <= 0:
            raise ValueError(f"page_size must be positive, got {page_size}")

        ingested: List[Dict[str, Any]] = []
        seen_batch_ids: Set[str] = set()

        # 計算歷史形成年限上限（冷戰起點至 30 年前法定基線）
        current_year = datetime.now(timezone.utc).year
        end_year = current_year - 30
        start_date = "1945-01-01"
        end_date = f"{end_year}-12-31"

        logger.info(f"[TNA] Target Covering Dates Horizon: {start_date} to {end_date} (Content date, not release timestamp)")

        for page_idx in range(max_pages):
            params = {
                "sps.searchQuery": "Cold War declassified foreign affairs",
                "sps.heldByFilter": "TNA",
                "sps.startDate": start_date,
                "sps.endDate": end_date,
                "sps.page": str(page_idx),
                "sps.resultsPageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                
                if not isinstance(payload, dict):
                    raise AdapterIngestionError(f"Unexpected payload type from TNA: {type(payload).__name__}")

                raw_records = payload.get("records")
                if raw_records is None:
                    if not ingested:
                        raise AdapterIngestionError(f"'records' field is null at page {page_idx} — Schema violation")
                    logger.warning(f"[TNA] 'records' became null at page {page_idx}. Halting pagination.")
                    break

                if not isinstance(raw_records, list):
                    raise AdapterIngestionError(f"Response schema violation: 'records' is {type(raw_records).__name__}")

                if not raw_records:
                    logger.info(f"[TNA] Reached end of stream at page {page_idx}.")
                    break

                current_batch_ids = {
                    item["id"] for item in raw_records 
                    if isinstance(item, dict) and item.get("id")
                }

                if not current_batch_ids:
                    logger.warning(f"[TNA] No valid record IDs found on page {page_idx}. Halting.")
                    break

                if current_batch_ids.issubset(seen_batch_ids):
                    logger.warning(f"[TNA] Duplicate batch encountered at page {page_idx}. Halting pagination.")
                    break
                seen_batch_ids.update(current_batch_ids)

                for item in raw_records:
                    if not isinstance(item, dict):
                        continue

                    doc_id = item.get("id")
                    reference = item.get("reference")
                    if not doc_id or not reference:
                        continue

                    clean_title = self.clean_html_markup(item.get("title"))
                    parts = str(reference).split("/")
                    fonds = parts[0].split()[0] if parts else "UNKNOWN"
                    series = parts[0] if parts else "UNKNOWN"

                    raw_dates = item.get("coveringDates")
                    covering_dates = (
                        raw_dates.strip()
                        if isinstance(raw_dates, str) and raw_dates.strip()
                        else f"1945-{end_year}"
                    )

                    record: Dict[str, Any] = {
                        "record_id": f"tna:{doc_id}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "The National Archives (Kew, Richmond)",
                                "zh": "英國國家檔案館 (Kew)"
                            },
                            "fonds": fonds,
                            "series": series,
                            "call_number": str(reference),
                            "title": {
                                "en": clean_title,
                                "zh": ""
                            },
                            "covering_dates": covering_dates
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Open_Government_Licence_v3",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Subject to UK Crown Copyright & OGL v3.0 conditions. Not formal legal advice.",
                                "zh": "受英國王室版權及 OGL v3.0 規範。非正式法律意見。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://discovery.nationalarchives.gov.uk/details/r/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                            "temporal_filter_semantic": "covering_dates_not_release_date"
                        }
                    }
                    ingested.append(record)

                time.sleep(0.3)

            except AdapterIngestionError as e:
                if not ingested:
                    raise
                logger.warning(f"[TNA] Ingestion stopped at page {page_idx} due to error: {e}")
                break
            except Exception as e:
                logger.error(f"[TNA] Page {page_idx} unexpected failure: {e}")
                if not ingested:
                    raise AdapterIngestionError(f"TNA pipeline initial acquisition failed: {e}") from e
                break

        logger.info(f"[TNA] Pipeline acquired {len(ingested)} distinct records.")
        return ingested
EOF
