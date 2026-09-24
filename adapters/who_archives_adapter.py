"""
World Health Organization (WHO Archives) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後全球天花消滅計劃、冷戰生化武器醫學防禦與跨國衛生主權公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.WHO")

class WhoArchivesIngestionError(Exception):
    pass

class WorldHealthOrganizationProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_WHO"
    # 世界衛生組織數位歷史檔案檢索 API (IRIS/Archives REST 端點)
    API_URL = "https://apps.who.int/iris/rest/search"
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
            return "Untitled WHO Historical Technical Report"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[WHO] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[WHO] IRIS gateway service maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise WhoArchivesIngestionError(f"WHO API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise WhoArchivesIngestionError("WHO retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # WHO 成立於 1948 年
        who_start = max(1948, int(start_year))
        logger.info(f"[WHO] Applying Historical Window: {who_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "query": "Biological Weapons Smallpox Eradication International Health Regulations",
                "startYear": str(who_start),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("items", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("handle", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title"))
                    call_no = doc.get("callNumber", f"WHO-ARCH-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"who:{doc_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "World Health Organization Archives (Geneva, Switzerland)",
                                "zh": "世界衛生組織歷史檔案處 (瑞士日內瓦)"
                            },
                            "fonds": "Executive Board and World Health Assembly Official Records Fonds",
                            "series": "跨國生化防護評估、天花根除計劃與衛生條例協商系列",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{who_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "WHO_Open_Access_Policy",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official documentation open under the World Health Organization Policy on Access to Information.",
                                "zh": "依世界衛生組織《資訊獲取政策》（20年解密原則）開放之國際衛生與科學檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://apps.who.int/iris/handle/10665/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[WHO] Batch isolated failure: {e}")
                break

        logger.info(f"[WHO] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
