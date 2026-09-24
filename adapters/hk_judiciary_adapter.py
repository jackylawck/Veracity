"""
Hong Kong Judiciary / Legal Information Institute (HKLII / Judiciary) Production Adapter
符合 BaseAdapter 統一時間窗口，採集香港戰後普通法判例、皇家特權司法爭訟與憲制判決書。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.HKJudiciary")

class HkJudiciaryIngestionError(Exception):
    pass

class HkJudiciaryProductionAdapter(BaseAdapter):
    NAME = "HK_JUDICIARY"
    # HKLII / 司法機構判例公開檢索 REST API
    API_URL = "https://www.hklii.hk/api/v1/cases/search"
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
            return "Untitled Judicial Ruling"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[HK_JUDICIARY] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[HK_JUDICIARY] Gateway service maintenance ({resp.status_code}).")
                    return {"cases": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise HkJudiciaryIngestionError(f"Judiciary API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise HkJudiciaryIngestionError("HK Judiciary retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_citations: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[HK_JUDICIARY] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Crown Privilege Constitutional Extradition Public Interest",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                cases = payload.get("cases", []) or payload.get("results", [])

                if not cases:
                    break

                for case in cases:
                    citation = str(case.get("citation") or case.get("id", "")).strip()
                    if not citation or citation in seen_citations:
                        continue
                    seen_citations.add(citation)

                    case_name = self.clean_text(case.get("title") or case.get("case_name"))
                    court = case.get("court", "Supreme Court of Hong Kong / Court of Final Appeal")
                    judgment_date = case.get("date", f"{start_year}-{end_year}")

                    record: Dict[str, Any] = {
                        "record_id": f"hkjudiciary:{citation.replace('/', '_').replace(' ', '').replace('[', '').replace(']', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Judiciary of the HKSAR / Supreme Court Library (Hong Kong)",
                                "zh": "香港特別行政區司法機構 / 高等法院圖書館 (金鐘)"
                            },
                            "fonds": "Hong Kong Law Reports & Constitutional Cases Fonds",
                            "series": "香港戰後普通法司法判例與憲制爭訟系列",
                            "call_number": citation,
                            "title": {
                                "en": f"[{court}] {case_name}",
                                "zh": None
                            },
                            "covering_dates": judgment_date
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "HK_Judicial_Open_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official judicial judgments released for public access and historical legal forensics under Common Law principles.",
                                "zh": "依普通法原則向公眾公開之法定判決書，供法律法證與歷史研究查閱。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.hklii.hk/en/cases/{citation}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[HK_JUDICIARY] Batch isolated failure: {e}")
                break

        logger.info(f"[HK_JUDICIARY] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
