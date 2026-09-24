"""
World Intellectual Property Organization (WIPO Archives, Geneva) Production Adapter
符合 BaseAdapter 統一時間窗口，採集巴黎公約、專利合作條約 (PCT) 與冷戰高科技技術轉讓多邊檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.WIPO")

class WipoArchivesIngestionError(Exception):
    pass

class WorldIntellectualPropertyOrganizationProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_WIPO"
    # 世界知識產權組織公開文獻檢索 REST API
    API_URL = "https://www.wipo.int/api/v1/archives/search"
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
            return "Untitled WIPO Multilateral Treaty Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[WIPO] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[WIPO] Archives service maintenance ({resp.status_code}).")
                    return {"documents": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise WipoArchivesIngestionError(f"WIPO API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise WipoArchivesIngestionError("WIPO retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[WIPO] Applying Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Patent Cooperation Treaty Intellectual Property Technology Transfer Paris Convention",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                documents = payload.get("documents", []) or payload.get("results", [])

                if not documents:
                    break

                for doc in documents:
                    doc_symbol = str(doc.get("symbol") or doc.get("id", "")).strip()
                    if not doc_symbol or doc_symbol in seen_ids:
                        continue
                    seen_ids.add(doc_symbol)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    governing_body = doc.get("governingBody", "WIPO General Assembly and Treaties Division")
                    call_no = doc.get("symbol", f"WIPO-DOC-{doc_symbol}")

                    record: Dict[str, Any] = {
                        "record_id": f"wipo:{doc_symbol.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "World Intellectual Property Organization Archives (Geneva)",
                                "zh": "世界知識產權組織歷史文獻庫 (瑞士日內瓦)"
                            },
                            "fonds": f"WIPO Diplomatic Conferences & Treaties Fonds ({governing_body})",
                            "series": "專利合作條約、巴黎公約修訂與高科技技術轉讓多邊公文系列",
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
                            "license_category": "WIPO_Public_Access_Policy",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified documentation made available under WIPO statutory publication mandates.",
                                "zh": "依世界知識產權組織法定資訊發佈準則公開之國際智財公約歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.wipo.int/treaties/en/documents/{doc_symbol}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[WIPO] Batch isolated failure: {e}")
                break

        logger.info(f"[WIPO] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
