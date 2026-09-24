"""
United Nations Treaty Series (UNTS / UN Treaty Collection) Production Adapter
符合 BaseAdapter 統一時間窗口，採集依《聯合國憲章》第102條法定登記註冊之主權條約與國際協定原卷。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.UNTS")

class UntsIngestionError(Exception):
    pass

class UnitedNationsTreatySeriesProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_UNTS"
    # 聯合國條約總彙官方公開檢索 REST API
    API_URL = "https://treaties.un.org/api/v1/treaties/search"
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
            return "Untitled Registered UN Sovereign Treaty"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[UNTS] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[UNTS] Treaty portal gateway maintenance ({resp.status_code}).")
                    return {"treaties": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise UntsIngestionError(f"UNTS API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise UntsIngestionError("UNTS retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[UNTS] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Security Boundary Defense Sovereignty Decolonization",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                treaties = payload.get("treaties", []) or payload.get("results", [])

                if not treaties:
                    break

                for doc in treaties:
                    reg_no = str(doc.get("registrationNumber") or doc.get("id", "")).strip()
                    if not reg_no or reg_no in seen_ids:
                        continue
                    seen_ids.add(reg_no)

                    clean_title = self.clean_text(doc.get("treatyTitle") or doc.get("title"))
                    participants = doc.get("participants", "Sovereign State Parties")
                    call_no = doc.get("registrationNumber", f"UNTS-REG-{reg_no}")

                    record: Dict[str, Any] = {
                        "record_id": f"unts:{reg_no.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "United Nations Treaty Collection (Treaty Section, New York)",
                                "zh": "聯合國條約總彙檔案庫 / 條約科 (紐約總部)"
                            },
                            "fonds": f"Registered Treaties Series ({participants})",
                            "series": "依《聯合國憲章》第102條登記註冊之主權國際協定全集",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("conclusionDate", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "UN_Charter_Art_102_Universal_Public_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Published pursuant to Article 102 of the Charter of the United Nations. Universal open public record.",
                                "zh": "依《聯合國憲章》第102條法定登記公佈之國際條約，屬全球通用之公開法定文獻。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://treaties.un.org/pages/showDetails.aspx?objid={reg_no}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[UNTS] Batch isolated failure: {e}")
                break

        logger.info(f"[UNTS] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
