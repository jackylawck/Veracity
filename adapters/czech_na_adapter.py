"""
National Archives of the Czech Republic (Národní archiv - NA CR) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後布拉格之春、華約軍隊入侵、秘密警察 (StB) 及前蘇聯核基地解密檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.CzechNA")

class CzechNaIngestionError(Exception):
    pass

class CzechNaProductionAdapter(BaseAdapter):
    NAME = "CZ_NA"
    # 捷克國家檔案館公開開放目錄 API (Badatelna/Vademecum 通用 REST 端點)
    API_URL = "https://vademecum.nacr.cz/api/v1/records/search"
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
            return "Untitled Czechoslovak State Archival Item"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[CZ_NA] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[CZ_NA] Vademecum portal maintenance ({resp.status_code}).")
                    return {"items": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise CzechNaIngestionError(f"Czech NA API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise CzechNaIngestionError("Czech NA retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[CZ_NA] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Studena valka Varsavska smlouva Prazske jaro StB odtajnene",
                "startYear": str(start_year),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("items", []) or payload.get("records", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("signatura", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    title_cz = self.clean_text(doc.get("title") or doc.get("nazev"))
                    fond_name = doc.get("fondName", "ÚV KSČ (Komunistická strana Československa) a MV")
                    call_no = doc.get("signatura", f"NACR-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"czna:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives of the Czech Republic (Prague)",
                                "zh": "捷克國家檔案館 (布拉格)"
                            },
                            "fonds": fond_name,
                            "series": doc.get("series", "冷戰華約侵略、捷共中央政治局與國家安全解密全宗"),
                            "call_number": call_no,
                            "title": {
                                "en": f"[Národní archiv] {title_cz}",
                                "zh": None
                            },
                            "covering_dates": doc.get("datace", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Czech_Act_499_2004_Coll_Archives",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Archival materials made accessible under Czech Act No. 499/2004 Coll. on Archival and Records Management.",
                                "zh": "依捷克《第 499/2004 號檔案暨紀錄管理法》法定解密公開之國家歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://vademecum.nacr.cz/vademecum/permalink?xid={doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[CZ_NA] Batch isolated failure: {e}")
                break

        logger.info(f"[CZ_NA] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
