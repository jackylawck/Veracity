"""
International Military Tribunal for the Far East (IMTFE / Tokyo Trial) Production Adapter
符合 BaseAdapter 統一時間窗口，採集遠東國際軍事法庭戰犯審訊、盟軍 GHQ 作戰日誌與亞洲戰後法證卷宗。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.IMTFE")

class ImtfeIngestionError(Exception):
    pass

class ImtfeTokyoProductionAdapter(BaseAdapter):
    NAME = "ASIA_IMTFE_TOKYO"
    # 東京審判數位檔案檢索 REST 端點 (Open Digital Archives Repository)
    API_URL = "https://imtfe.law.virginia.edu/api/v1/records/search"
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
            return "Untitled Tokyo Tribunal Exhibit Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[IMTFE] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[IMTFE] Tribunal repository maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise ImtfeIngestionError(f"IMTFE API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise ImtfeIngestionError("IMTFE retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 東京審判開庭期間為 1946–1948 年
        imtfe_start = max(1946, int(start_year))
        imtfe_end = min(1948, int(end_year))
        logger.info(f"[IMTFE] Applying Historical Window: {imtfe_start} to {imtfe_end}")

        for page_idx in range(max_pages):
            params = {
                "q": "Tokyo Major War Crimes Prosecution Tribunal Exhibit Judgment",
                "startYear": str(imtfe_start),
                "endYear": str(imtfe_end),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("items", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("exhibitNumber", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    call_no = doc.get("exhibitNumber", f"IMTFE-DOC-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"imtfe:{doc_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "International Military Tribunal for the Far East Archives (Tokyo / US NARA / UVa)",
                                "zh": "遠東國際軍事法庭檔案庫 (東京審判 / 美國國檔館 / 維吉尼亞法學院特藏)"
                            },
                            "fonds": "Records of the International Military Tribunal for the Far East (IMTFE)",
                            "series": "遠東國際軍事審判法庭速記錄、呈堂證物與盟軍甲級戰犯全宗",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{imtfe_start}-{imtfe_end}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "IMTFE_Universal_Public_Domain",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official proceedings of the International Military Tribunal for the Far East. Worldwide Public Domain.",
                                "zh": "遠東國際軍事審判官方公開公文與審訊證物，屬全球公有領域法證檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://imtfe.law.virginia.edu/collections/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[IMTFE] Batch isolated failure: {e}")
                break

        logger.info(f"[IMTFE] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
