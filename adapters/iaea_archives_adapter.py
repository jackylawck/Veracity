"""
International Atomic Energy Agency (IAEA Archives) Production Adapter
符合 BaseAdapter 統一時間窗口，採集原子能監督、核不擴散條約 (NPT) 談判與核能歷史解密公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.IAEA")

class IaeaArchivesIngestionError(Exception):
    pass

class IaeaArchivesProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_IAEA"
    # 國際原子能總署公開官方公文檢索 API
    API_URL = "https://www.iaea.org/api/v1/records/historical-search"
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
            return "Untitled IAEA Declassified Nuclear Safeguard Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[IAEA] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[IAEA] Portal gateway offline ({resp.status_code}).")
                    return {"records": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise IaeaArchivesIngestionError(f"IAEA API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise IaeaArchivesIngestionError("IAEA retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # IAEA 於 1957 年成立，起始年份設為 1957
        iaea_start = max(1957, int(start_year))
        logger.info(f"[IAEA] Applying Historical Window: {iaea_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "query": "Nuclear Non-Proliferation Safeguards Board of Governors Treaty",
                "startYear": str(iaea_start),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("records", []) or payload.get("items", [])

                if not records:
                    break

                for doc in records:
                    doc_symbol = str(doc.get("symbol") or doc.get("id", "")).strip()
                    if not doc_symbol or doc_symbol in seen_ids:
                        continue
                    seen_ids.add(doc_symbol)

                    clean_title = self.clean_text(doc.get("title"))
                    fonds_name = doc.get("fonds", "IAEA Board of Governors & General Conference Official Records")
                    call_no = doc.get("symbol", f"IAEA-{doc_symbol}")

                    record: Dict[str, Any] = {
                        "record_id": f"iaea:{doc_symbol.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "International Atomic Energy Agency Archives (Vienna)",
                                "zh": "國際原子能總署歷史檔案處 (維也納)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("series", "Nuclear Safeguards & Non-Proliferation Inspection Series"),
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{iaea_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "IAEA_Official_Public_Documents",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official public documentation issued by the IAEA under its statutory disclosure mandates.",
                                "zh": "依國際原子能總署法定資訊揭露準則公開之官方解密公文。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.iaea.org/publications/documents/{doc_symbol}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[IAEA] Batch isolated failure: {e}")
                break

        logger.info(f"[IAEA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
