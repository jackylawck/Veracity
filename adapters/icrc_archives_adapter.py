"""
International Committee of the Red Cross (ICRC Archives) Production Adapter
符合 BaseAdapter 統一時間窗口，採集日內瓦公約、戰後戰俘視察報告與國際武裝衝突解密人道檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ICRC")

class IcrcArchivesIngestionError(Exception):
    pass

class IcrcArchivesProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_ICRC"
    # 紅十字國際委員會公共歷史檔案檢索 REST 端點
    API_URL = "https://archives.icrc.org/api/v1/records/search"
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
            return "Untitled ICRC Humanitarian Archival Dossier"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[ICRC] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[ICRC] Archive gateway offline ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise IcrcArchivesIngestionError(f"ICRC API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise IcrcArchivesIngestionError("ICRC retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[ICRC] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Prisoners of War Geneva Conventions Conflict Mission",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("items", [])

                if not records:
                    break

                for doc in records:
                    ref_code = str(doc.get("reference") or doc.get("id", "")).strip()
                    if not ref_code or ref_code in seen_ids:
                        continue
                    seen_ids.add(ref_code)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    fonds_name = doc.get("fonds", "General Archives of the International Committee of the Red Cross")
                    call_no = doc.get("reference", f"ICRC-DOC-{ref_code}")

                    record: Dict[str, Any] = {
                        "record_id": f"icrc:{ref_code.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "International Committee of the Red Cross Archives (Geneva)",
                                "zh": "紅十字國際委員會檔案館 (日內瓦)"
                            },
                            "fonds": fonds_name,
                            "series": doc.get("series", "Post-1945 Armed Conflict Protection Series (B CR / B AG)"),
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("coveringDates", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "ICRC_Public_Archives_Rules",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified records opened under ICRC Rules on Access to Archives (40-year general declassification).",
                                "zh": "依紅十字國際委員會《檔案查閱規則》（40年法定解密窗口）開放之公開歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://archives.icrc.org/dossier/{ref_code}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[ICRC] Batch isolated failure: {e}")
                break

        logger.info(f"[ICRC] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
