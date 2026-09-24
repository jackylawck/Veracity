"""
World Trade Organization & GATT Historical Archives (WTO/GATT, Geneva) Production Adapter
符合 BaseAdapter 統一時間窗口，採集 1947 年關貿總協定 (GATT)、關稅談判多邊備忘錄與貿易爭端裁決原件。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.WTOGATT")

class WtoGattIngestionError(Exception):
    pass

class WorldTradeOrganizationGattProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_WTO_GATT"
    # WTO/GATT 歷史解密檔案官方檢索 REST API (GATT Digital Archive)
    API_URL = "https://www.wto.org/api/v1/gatt-archive/search"
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
            return "Untitled GATT/WTO Multilateral Trade Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[WTO_GATT] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[WTO_GATT] Archive endpoint maintenance ({resp.status_code}).")
                    return {"documents": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise WtoGattIngestionError(f"WTO GATT API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise WtoGattIngestionError("WTO GATT retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # GATT 於 1947 年簽署成立
        gatt_start = max(1947, int(start_year))
        logger.info(f"[WTO_GATT] Applying Historical Window: {gatt_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Tariff Negotiation Security Exceptions Article XXI Dispute Settlement",
                "startYear": str(gatt_start),
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
                    symbol = str(doc.get("documentSymbol") or doc.get("id", "")).strip()
                    if not symbol or symbol in seen_ids:
                        continue
                    seen_ids.add(symbol)

                    clean_title = self.clean_text(doc.get("title") or doc.get("description"))
                    call_no = doc.get("documentSymbol", f"GATT-DOC-{symbol}")

                    record: Dict[str, Any] = {
                        "record_id": f"wtogatt:{symbol.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "World Trade Organization Archives / GATT Digital Archive (Geneva)",
                                "zh": "世界貿易組織歷史檔案處 / 關貿總協定數位檔案庫 (瑞士日內瓦)"
                            },
                            "fonds": "General Agreement on Tariffs and Trade (GATT 1947) Official Records",
                            "series": "多邊關稅談判回合、安全例外條款審議與貿易爭端小組裁決系列",
                            "call_number": call_no,
                            "title": {
                                "en": clean_title,
                                "zh": None
                            },
                            "covering_dates": doc.get("dateDisplay", f"{gatt_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "WTO_GATT_Declassified_Public_Record",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified official records of the GATT/WTO freely open for research and international trade forensics.",
                                "zh": "依世貿組織法定解密規章公佈之關貿總協定歷史公文，供國際貿易法證與歷史研究。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.wto.org/gattdocs/{symbol}.pdf",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[WTO_GATT] Batch isolated failure: {e}")
                break

        logger.info(f"[WTO_GATT] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
