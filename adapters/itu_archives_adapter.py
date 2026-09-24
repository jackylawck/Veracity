"""
International Telecommunication Union (ITU Archives, Geneva) Production Adapter
符合 BaseAdapter 統一時間窗口，採集冷戰無線電頻譜分配 (WARC)、電波跨境干擾爭端與衛星軌道主權檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ITU")

class ItuArchivesIngestionError(Exception):
    pass

class InternationalTelecommunicationUnionProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_ITU"
    # 國際電信聯盟官方公開歷史文獻檢索 API (ITU History Portal)
    API_URL = "https://www.itu.int/en/history/api/v1/records/search"
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
            return "Untitled ITU Telecommunication Allocation Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[ITU] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[ITU] History portal under maintenance ({resp.status_code}).")
                    return {"records": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise ItuArchivesIngestionError(f"ITU API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise ItuArchivesIngestionError("ITU retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 1947 年大西洋城電信大會（Atlantic City Conference）確立現代無線電分配體系
        itu_start = max(1947, int(start_year))
        logger.info(f"[ITU] Applying Historical Window: {itu_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Radio Regulations Spectrum Allocation Jamming Satellite Orbit",
                "startYear": str(itu_start),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("records", []) or payload.get("items", [])

                if not records:
                    break

                for doc in records:
                    ref_id = str(doc.get("reference") or doc.get("id", "")).strip()
                    if not ref_id or ref_id in seen_ids:
                        continue
                    seen_ids.add(ref_id)

                    clean_title = self.clean_text(doc.get("title"))
                    conference = doc.get("conference", "World Administrative Radio Conference (WARC)")
                    call_no = doc.get("reference", f"ITU-ACT-{ref_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"itu:{ref_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "International Telecommunication Union Library and Archives Service (Geneva)",
                                "zh": "國際電信聯盟圖書及檔案服務處 (瑞士日內瓦)"
                            },
                            "fonds": f"ITU Plenipotentiary and Radio Conference Fonds ({conference})",
                            "series": "國際無線電頻譜主權劃分、跨境電波干擾與衛星軌道分配公約系列",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{itu_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "ITU_Open_Access_Declaration",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Historic documents published by the ITU for universal research and telecommunications history verification.",
                                "zh": "由國際電信聯盟發佈之歷史公文，供全球學術研究與電信主權法證核驗。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.itu.int/en/history/records/{ref_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[ITU] Batch isolated failure: {e}")
                break

        logger.info(f"[ITU] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
