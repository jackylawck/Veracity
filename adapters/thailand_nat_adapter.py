"""
National Archives of Thailand (NAT / สำนักหอจดหมายเหตุแห่งชาติ) Production Adapter
符合 BaseAdapter 統一時間窗口，採集東南亞條約組織 (SEATO)、越戰後勤支援與戰後泰美防衛協定公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.NAT")

class NatArchivesIngestionError(Exception):
    pass

class ThailandNatProductionAdapter(BaseAdapter):
    NAME = "ASIA_NAT"
    # 泰國國家檔案館官方公開目錄 API (Fine Arts Department Open Data)
    API_URL = "https://nat.finearts.go.th/api/v1/archives/search"
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
            return "Untitled Thai National Archival Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[NAT] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[NAT] Catalog gateway maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise NatArchivesIngestionError(f"NAT API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise NatArchivesIngestionError("NAT retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[NAT] Applying Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "SEATO Treaty Foreign Affairs Cold War Defense",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    item_id = str(doc.get("id") or doc.get("archiveCode", "")).strip()
                    if not item_id or item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    title_th = self.clean_text(doc.get("title") or doc.get("name"))
                    ministry = doc.get("creator", "Ministry of Foreign Affairs / Prime Minister's Office")
                    call_no = doc.get("archiveCode", f"NAT-TH-{item_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"thnat:{item_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives of Thailand (Bangkok)",
                                "zh": "泰國國家檔案館 (曼谷)"
                            },
                            "fonds": f"Royal Thai Government Central Archives ({ministry})",
                            "series": "東南亞條約組織 (SEATO) 總部、冷戰共同防衛與外交檔案系列",
                            "call_number": call_no,
                            "title": {
                                "en": f"[National Archives of Thailand] {title_th}",
                                "zh": None
                            },
                            "covering_dates": doc.get("dateRange", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Thailand_Official_Information_Act_1997",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified state records disclosed under the Official Information Act, B.E. 2540 (1997).",
                                "zh": "依泰國佛曆 2540 年（1997年）《官方資訊法》法定解密開放之政府歷史公文。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://nat.finearts.go.th/item/{item_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[NAT] Batch isolated failure: {e}")
                break

        logger.info(f"[NAT] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
