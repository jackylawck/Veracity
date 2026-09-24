"""
International Labour Organization (ILO Archives, Geneva) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後廢除強迫勞動、結社自由調查與國際勞工公約法定原卷。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ILO")

class IloArchivesIngestionError(Exception):
    pass

class InternationalLabourOrganizationProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_ILO"
    # 國際勞工組織歷史文檔檢索 REST API (Labordoc / ILO Archives)
    API_URL = "https://labordoc.ilo.org/api/v1/records/search"
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
            return "Untitled ILO Convention or Inquiry Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[ILO] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[ILO] Portal maintenance window ({resp.status_code}).")
                    return {"records": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise IloArchivesIngestionError(f"ILO API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise IloArchivesIngestionError("ILO retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[ILO] Applying Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Freedom of Association Forced Labour Commission of Inquiry Convention",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("records", []) or payload.get("results", [])

                if not records:
                    break

                for doc in records:
                    rec_id = str(doc.get("referenceNo") or doc.get("id", "")).strip()
                    if not rec_id or rec_id in seen_ids:
                        continue
                    seen_ids.add(rec_id)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    fonds_name = doc.get("fonds", "Governing Body of the International Labour Office")
                    call_no = doc.get("referenceNo", f"ILO-GB-{rec_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"ilo:{rec_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "International Labour Organization Archives (Geneva, Switzerland)",
                                "zh": "國際勞工組織歷史檔案部 (瑞士日內瓦)"
                            },
                            "fonds": fonds_name,
                            "series": "國際勞工大會、結社自由委員會審查調查與人權公約全宗",
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
                            "license_category": "ILO_Public_Access_Policy",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official documentation opened under the ILO Policy on Access to Archives (20-year general declassification).",
                                "zh": "依國際勞工組織《檔案查閱政策》（20年法定解密原則）開放之國際勞工人權檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://labordoc.ilo.org/record/{rec_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[ILO] Batch isolated failure: {e}")
                break

        logger.info(f"[ILO] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
