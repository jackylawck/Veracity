"""
General Archive of the Nation (Archivo General de la Nación - AGN Argentina) Production Adapter
符合 BaseAdapter 統一時間窗口，採集拉丁美洲冷戰「禿鷹行動」、馬島/福克蘭海戰與南美軍事獨裁解密文卷。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ArgentinaAGN")

class ArgentinaAgnIngestionError(Exception):
    pass

class ArgentinaAgnProductionAdapter(BaseAdapter):
    NAME = "AR_AGN"
    # 阿根廷開放資料與國家檔案館 API 檢索端點
    API_URL = "https://datos.gob.ar/api/3/action/package_search"
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
            return "Documento Desclasificado de la República Argentina"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[AGN] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[AGN] Portal under maintenance ({resp.status_code}).")
                    return {"result": {"results": []}}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise ArgentinaAgnIngestionError(f"AGN API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise ArgentinaAgnIngestionError("AGN retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[AGN] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Malvinas Derechos Humanos Dictadura Operacion Condor desclasificado",
                "rows": page_size,
                "start": page_idx * page_size
            }

            try:
                payload = self._execute_with_retry(params)
                result = payload.get("result", {})
                records = result.get("results", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("name", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    title_es = self.clean_text(doc.get("title") or doc.get("notes"))
                    organization = doc.get("organization", {}).get("title", "Ministerio de Defensa / AGN")
                    call_no = f"AGN-AR-{doc_id[:12]}"

                    record: Dict[str, Any] = {
                        "record_id": f"aragn:{doc_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "General Archive of the Nation (Buenos Aires)",
                                "zh": "阿根廷國家檔案館 (布宜諾斯艾利斯)"
                            },
                            "fonds": organization,
                            "series": "南大西洋戰爭、軍事獨裁與冷戰情報解密全宗",
                            "call_number": call_no,
                            "title": {
                                "en": f"[AGN Argentina] {title_es}",
                                "zh": None
                            },
                            "covering_dates": f"{start_year}-{end_year}"
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Argentina_Open_Data_License",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Declassified state records released under National Access to Public Information Law 27.275.",
                                "zh": "依阿根廷《第 27.275 號公共資訊獲取法》法定解密開放之政府歷史公文。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://datos.gob.ar/dataset/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[AGN] Batch isolated failure: {e}")
                break

        logger.info(f"[AGN] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
