"""
National Archives of the Republic of Indonesia (Arsip Nasional Republik Indonesia - ANRI) Production Adapter
符合 BaseAdapter 統一時間窗口，採集 1955 年萬隆亞非會議、印荷主權移交與不結盟運動建政解密檔案。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ANRI")

class AnriArchivesIngestionError(Exception):
    pass

class IndonesiaAnriProductionAdapter(BaseAdapter):
    NAME = "ASIA_ANRI"
    # 印尼國家檔案館公開開放目錄 API (SIKID / ANRI Open Data REST 端點)
    API_URL = "https://anri.go.id/api/v1/records/search"
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
            return "Arsip Sejarah Republik Indonesia (Untitled Archival Item)"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[ANRI] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[ANRI] Portal service maintenance ({resp.status_code}).")
                    return {"data": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise AnriArchivesIngestionError(f"ANRI API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise AnriArchivesIngestionError("ANRI retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 1945 年 8 月 17 日印尼宣佈獨立
        anri_start = max(1945, int(start_year))
        logger.info(f"[ANRI] Applying Historical Window: {anri_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "q": "Konferensi Asia Afrika KAA 1955 Non-Blok Kedaulatan Dekolonisasi",
                "startYear": str(anri_start),
                "endYear": str(end_year),
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("data", []) or payload.get("results", [])

                if not records:
                    break

                for doc in records:
                    doc_id = str(doc.get("id") or doc.get("nomorBerkas", "")).strip()
                    if not doc_id or doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    title_id = self.clean_text(doc.get("judul") or doc.get("title"))
                    fonds_name = doc.get("namaFonds", "Fonds Kabinet Perdana Menteri & Konferensi Asia-Afrika")
                    call_no = doc.get("nomorBerkas", f"ANRI-KAA-{doc_id}")

                    record: Dict[str, Any] = {
                        "record_id": f"anri:{doc_id.replace('/', '_').replace(' ', '').replace(':', '_')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "National Archives of the Republic of Indonesia (Jakarta)",
                                "zh": "印尼國家檔案館 (雅加達)"
                            },
                            "fonds": fonds_name,
                            "series": "萬隆亞非會議檔案（UNESCO世界記憶名錄）與獨立建國主權系列",
                            "call_number": call_no,
                            "title": {
                                "en": f"[ANRI Indonesia] {title_id}",
                                "zh": None
                            },
                            "covering_dates": doc.get("tahun", f"{anri_start}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Indonesia_Law_43_2009_Archives",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Public archival documents disclosed under Republic of Indonesia Law No. 43/2009 on Archives.",
                                "zh": "依印尼共和國《2009年第43號檔案法》法定解密公開之國家歷史檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://anri.go.id/publikasi/arsip/{doc_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[ANRI] Batch isolated failure: {e}")
                break

        logger.info(f"[ANRI] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
