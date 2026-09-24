"""
German Federal Archives (Bundesarchiv - BArch) Production Adapter
符合 BaseAdapter 統一時間窗口，採集戰後西德聯邦總理府、東西德分裂與兩德統一部分解密公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.GermanyBArch")

class GermanyBarchIngestionError(Exception):
    pass

class GermanyBarchProductionAdapter(BaseAdapter):
    NAME = "DE_BARCH"
    # 德國聯邦檔案館公開開放檢索端點 (Invenio API 通道)
    API_URL = "https://invenio.bundesarchiv.de/api/v1/records/search"
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
            return "Untitled Bundesarchiv Record"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[BArch] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[BArch] Invenio service maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise GermanyBarchIngestionError(f"Bundesarchiv API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise GermanyBarchIngestionError("Bundesarchiv retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[BArch] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Kalter Krieg Bundeskanzleramt Außenpolitik declassified",
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
                    signatur = str(doc.get("signatur") or doc.get("id", "")).strip()
                    if not signatur or signatur in seen_ids:
                        continue
                    seen_ids.add(signatur)

                    clean_title = self.clean_text(doc.get("titel") or doc.get("title"))
                    bestand = doc.get("bestand", "B 136 (Bundeskanzleramt)")
                    dates = doc.get("laufzeit", f"{start_year}-{end_year}")

                    record: Dict[str, Any] = {
                        "record_id": f"debarch:{signatur.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "German Federal Archives (Koblenz & Berlin-Lichterfelde)",
                                "zh": "德國聯邦檔案館 (科布倫茲與柏林)"
                            },
                            "fonds": bestand,
                            "series": doc.get("klassifikation", "Nachkriegszeit und Bundesrepublik Deutschland"),
                            "call_number": signatur,
                            "title": {
                                "en": f"[Bundesarchiv] {clean_title}",
                                "zh": None
                            },
                            "covering_dates": dates
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "German_Federal_Archives_Open_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Archival materials made accessible under the Federal Archives Act (Bundesarchivgesetz - BArchG).",
                                "zh": "依德國《聯邦檔案法》（BArchG）法定解密開放之公共歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://invenio.bundesarchiv.de/basys2-invenio/direktlink/{signatur}/",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[BArch] Batch isolated failure: {e}")
                break

        logger.info(f"[BArch] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
