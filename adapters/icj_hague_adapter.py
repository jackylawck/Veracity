"""
International Court of Justice (ICJ / Peace Palace) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後國家間主權領土爭議、海洋劃界與國際法解密判決及證據卷宗。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ICJ")

class IcjIngestionError(Exception):
    pass

class InternationalCourtJusticeProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_ICJ"
    # 國際法院官方公開案件與歷史判決檢索 REST API
    API_URL = "https://www.icj-cij.org/api/v1/cases/search"
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
            return "Untitled ICJ Contentious Proceeding Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[ICJ] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[ICJ] Judicial portal maintenance ({resp.status_code}).")
                    return {"cases": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise IcjIngestionError(f"ICJ API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise IcjIngestionError("ICJ retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[ICJ] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Territorial Dispute Sovereignty Maritime Boundary Treaty",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                cases = payload.get("cases", []) or payload.get("results", [])

                if not cases:
                    break

                for doc in cases:
                    case_id = str(doc.get("id") or doc.get("caseNumber", "")).strip()
                    if not case_id or case_id in seen_ids:
                        continue
                    seen_ids.add(case_id)

                    clean_title = self.clean_text(doc.get("title") or doc.get("name"))
                    case_no = doc.get("caseNumber", f"ICJ-CASE-{case_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"icj:{case_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "International Court of Justice Archives, Peace Palace (The Hague)",
                                "zh": "海牙國際法院歷史檔案部 / 和平宮 (海牙)"
                            },
                            "fonds": "ICJ Contentious Cases & Advisory Proceedings Fonds",
                            "series": "主權領土爭端、軍事干預與條約爭訟系列",
                            "call_number": case_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "ICJ_Public_Judicial_Records",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official judicial records and pleadings published under ICJ Rules of Court for universal open access.",
                                "zh": "依國際法院規約公開之國際司法訴狀、判決與爭議檔案，供全球公眾檢驗。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.icj-cij.org/case/{case_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[ICJ] Batch isolated failure: {e}")
                break

        logger.info(f"[ICJ] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
