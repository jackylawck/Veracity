"""
Stasi Records Agency (Bundesarchiv - Stasi-Unterlagen-Archiv / BStU) Production Adapter
符合 BaseAdapter 統一時間窗口，採集前東德國家安全部 (Stasi/MfS) 冷戰間諜監聽、秘密審訊與跨國特工解密檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.StasiBStU")

class StasiBstuIngestionError(Exception):
    pass

class StasiBstuProductionAdapter(BaseAdapter):
    NAME = "DE_STASI_BSTU"
    # 史塔西檔案局官方數位檢索端點 (Stasi-Mediathek REST API)
    API_URL = "https://www.stasi-mediathek.de/api/v1/records/search"
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
            return "Untitled Stasi / MfS Intelligence Dossier"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[StasiBStU] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[StasiBStU] Mediathek gateway maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise StasiBstuIngestionError(f"Stasi BStU API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise StasiBstuIngestionError("Stasi BStU retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 史塔西於 1950 年成立，至 1990 年東德瓦解
        stasi_start = max(1950, int(start_year))
        stasi_end = min(1990, int(end_year))
        logger.info(f"[StasiBStU] Applying Historical Window: {stasi_start} to {stasi_end}")

        for page_idx in range(max_pages):
            params = {
                "q": "Spionage Abwehr Hauptverwaltung Aufklaerung HVA",
                "startYear": str(stasi_start),
                "endYear": str(stasi_end),
                "page": str(page_idx + 1),
                "pageSize": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("results", []) or payload.get("items", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("signatur", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    clean_title = self.clean_text(doc.get("titel") or doc.get("title"))
                    signatur = doc.get("signatur", f"BStU-MfS-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"stasi:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Stasi Records Agency / German Federal Archives (Berlin-Lichtenberg)",
                                "zh": "德國聯邦檔案館史塔西檔案部 / 原前東德秘密警察檔案局 (柏林)"
                            },
                            "fonds": "Ministerium für Staatssicherheit (MfS / Stasi) Fonds",
                            "series": "外國情報局 (HVA) 與國家安全部跨國間諜監視全宗",
                            "call_number": signatur,
                            "title": {
                                "en": f"[Stasi MfS] {clean_title}",
                                "zh": None
                            },
                            "covering_dates": doc.get("datierung", f"{stasi_start}-{stasi_end}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Stasi_Records_Act_StUG_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Preserved and disclosed under the Stasi Records Act (Stasi-Unterlagen-Gesetz - StUG) for public reckoning and historical forensics.",
                                "zh": "依德國《史塔西檔案法》（StUG）法定解密開放之情報檔案，供歷史清算與法證核驗。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.stasi-mediathek.de/medien/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[StasiBStU] Batch isolated failure: {e}")
                break

        logger.info(f"[StasiBStU] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
