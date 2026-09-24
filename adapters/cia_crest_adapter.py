"""
CIA Freedom of Information Act Electronic Reading Room (CREST System) Production Adapter
符合 BaseAdapter 統一時間窗口，採集美國中央情報局 (CIA) 歷史解密冷戰情報、每日總統簡報與秘密軍事評估。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.CIACREST")

class CiaCrestIngestionError(Exception):
    pass

class CiaCrestProductionAdapter(BaseAdapter):
    NAME = "US_CIA_CREST"
    # CIA FOIA Electronic Reading Room 公開檢索 API 端點
    API_URL = "https://www.cia.gov/readingroom/api/records/search"
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
            return "Untitled Declassified CIA Intelligence Briefing"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[CIA_CREST] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[CIA_CREST] Portal maintenance window ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise CiaCrestIngestionError(f"CIA CREST API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise CiaCrestIngestionError("CIA CREST retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # CIA 成立於 1947 年（國家安全法），設 1947 為起始點
        cia_start = max(1947, int(start_year))
        logger.info(f"[CIA_CREST] Applying Historical Window: {cia_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "keywords": "Soviet China Crisis Nuclear Intelligence Estimate",
                "start_year": str(cia_start),
                "end_year": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("documentNumber") or doc.get("id", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("title"))
                    call_no = doc.get("documentNumber", f"CIA-RDP-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"ciacrest:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Central Intelligence Agency CREST Reading Room (Langley, Virginia)",
                                "zh": "美國中央情報局 CREST 數位法證閱覽室 (維吉尼亞州蘭利)"
                            },
                            "fonds": "CIA Directorate of Intelligence Declassified Records",
                            "series": "冷戰國家情報評估 (NIE) 與每日總統情報簡報 (PDB) 系列",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("publicationDate", f"{cia_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "US_Public_Domain_CIA_CREST",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified historical intelligence documents released under Executive Order 13526 and FOIA.",
                                "zh": "依美國第 13526 號行政命令及《資訊自由法》法定解密之中央情報局歷史公文。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.cia.gov/readingroom/document/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[CIA_CREST] Batch isolated failure: {e}")
                break

        logger.info(f"[CIA_CREST] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
