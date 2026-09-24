"""
International Tribunal for the Law of the Sea (ITLOS Archives, Hamburg) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後聯合國海洋法公約 (UNCLOS)、專屬經濟區與海洋劃界司法判決原卷。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ITLOS")

class ItlosArchivesIngestionError(Exception):
    pass

class InternationalTribunalLawSeaProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_ITLOS"
    # 國際海洋法法庭公開判決與案件檢索 REST API
    API_URL = "https://www.itlos.org/api/v1/cases/search"
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
            return "Untitled ITLOS Law of the Sea Proceeding"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[ITLOS] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[ITLOS] Portal gateway maintenance ({resp.status_code}).")
                    return {"cases": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise ItlosArchivesIngestionError(f"ITLOS API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise ItlosArchivesIngestionError("ITLOS retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[ITLOS] Applying Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Maritime Boundary Delimitation Fisheries UNCLOS Prompt Release",
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
                    case_no = str(doc.get("caseNumber") or doc.get("id", "")).strip()
                    if not case_no or case_no in seen_ids:
                        continue
                    seen_ids.add(case_no)

                    clean_title = self.clean_text(doc.get("caseTitle") or doc.get("name"))
                    parties = doc.get("stateParties", "States Parties to UNCLOS")
                    call_no = f"ITLOS-CASE-{case_no}"

                    record: Dict[str, Any] = {
                        "record_id": f"itlos:{case_no.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "International Tribunal for the Law of the Sea Archives (Hamburg, Germany)",
                                "zh": "國際海洋法法庭檔案處 (德國漢堡)"
                            },
                            "fonds": f"ITLOS Judicial Proceedings and Delimitation Fonds ({parties})",
                            "series": "國際海洋法公約爭端、專屬經濟區與領海主權終審判決系列",
                            "call_number": call_no,
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
                            "license_category": "ITLOS_Statutory_Public_Judicial_Record",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official judicial decisions and records of the ITLOS under UNCLOS mandates. Worldwide public domain.",
                                "zh": "依《聯合國海洋法公約》法定公開之國際海洋法庭判決與訴訟紀錄。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.itlos.org/en/main/cases/list-of-cases/case-no-{case_no}/",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[ITLOS] Batch isolated failure: {e}")
                break

        logger.info(f"[ITLOS] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
