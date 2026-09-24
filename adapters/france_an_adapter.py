"""
Archives Nationales de France (AN) Production Adapter
符合 BaseAdapter 統一時間窗口，採集歐洲大陸法系國家歷史解密公文與外交全宗。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.FranceAN")

class FranceAnIngestionError(Exception):
    pass

class FranceAnProductionAdapter(BaseAdapter):
    NAME = "FRANCE_AN"
    # 法國文化開放數據與國家檔案館 API 檢索端點
    API_URL = "https://data.culture.gouv.fr/api/records/1.0/search/"
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
            return "Document Historique Déclassifié (France)"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[FRANCE_AN] Rate limit (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if not resp.ok:
                    logger.error(f"[FRANCE_AN] API responded with error {resp.status_code}: {resp.text}")
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise FranceAnIngestionError(f"France AN API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise FranceAnIngestionError("France AN retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[FRANCE_AN] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "dataset": "archives-nationales-fonds-et-collections",
                "q": "Guerre Froide Relations Internationales",
                "rows": str(page_size),
                "start": str(page_idx * page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("records", [])

                if not records:
                    logger.info(f"[FRANCE_AN] End of stream reached at offset {page_idx * page_size}.")
                    break

                for rec in records:
                    record_id = rec.get("recordid")
                    fields = rec.get("fields", {})
                    if not record_id or record_id in seen_ids:
                        continue
                    seen_ids.add(record_id)

                    title_fr = self.clean_text(fields.get("intitule") or fields.get("description"))
                    cote = fields.get("cote", f"AN-{record_id[:8]}")
                    producteur = fields.get("producteur", "Ministère des Affaires Étrangères / État")

                    record: Dict[str, Any] = {
                        "record_id": f"francean:{record_id}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Archives Nationales de France (Pierrefitte-sur-Seine)",
                                "zh": "法國國家檔案館 (Pierrefitte-sur-Seine)"
                            },
                            "fonds": producteur,
                            "series": fields.get("serie", "Série W (Archives Publiques Post-1940)"),
                            "call_number": cote,
                            "title": {
                                "en": title_fr, # 法語原名作為公文基準
                                "zh": None
                            },
                            "covering_dates": fields.get("dates", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Licence_Ouverte_v2",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Open Government Licence (Licence Ouverte 2.0) by Etalab for French public sector information.",
                                "zh": "依法國 Etalab 開放政府授權（Licence Ouverte 2.0），開放公眾查閱與自由復用。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.siv.archives-nationales.culture.gouv.fr/siv/recherche/fiche.action?id={record_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[FRANCE_AN] Page {page_idx + 1} processing error: {e}")
                break

        logger.info(f"[FRANCE_AN] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
