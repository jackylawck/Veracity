"""
Japan Center for Asian Historical Records (JACAR / National Archives of Japan) Adapter
符合 BaseAdapter 統一時間窗口，採集戰後日本外務省及防衛省亞洲歷史解密公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.JACAR")

class JacarIngestionError(Exception):
    pass

class JacarProductionAdapter(BaseAdapter):
    NAME = "ASIA_JACAR"
    # JACAR 開放檢索 API 端點
    API_URL = "https://www.jacar.go.jp/api/v1/records/search"
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
            return "Untitled Asian Historical Official Document"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[JACAR] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[JACAR] Gateway offline ({resp.status_code}).")
                    return {"records": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise JacarIngestionError(f"JACAR API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise JacarIngestionError("JACAR retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_codes: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[JACAR] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "keyword": "外交 外務省 冷戦 講和条約",
                "startYear": start_year,
                "endYear": end_year,
                "page": str(page_idx + 1),
                "limit": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                records = payload.get("records", []) or payload.get("items", [])

                if not records:
                    break

                for doc in records:
                    ref_code = str(doc.get("refCode") or doc.get("id", "")).strip()
                    if not ref_code or ref_code in seen_codes:
                        continue
                    seen_codes.add(ref_code)

                    title_jp = self.clean_text(doc.get("titleJa") or doc.get("title"))
                    title_en = doc.get("titleEn")
                    display_title_en = self.clean_text(title_en) if title_en else f"[JACAR] {title_jp}"

                    origin_agency = doc.get("organization", "外務省外交史料館 / 防衛研究所")
                    fonds_name = doc.get("series", "戦後外交記録・極東関係公文全宗")

                    record: Dict[str, Any] = {
                        "record_id": f"jacar:{ref_code.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Japan Center for Asian Historical Records (Tokyo)",
                                "zh": "日本國立公文書館亞洲歷史資料中心 (東京)"
                            },
                            "fonds": origin_agency,
                            "series": fonds_name,
                            "call_number": ref_code,
                            "title": {
                                "en": display_title_en,
                                "zh": title_jp
                            },
                            "covering_dates": doc.get("dateDisplay", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Japan_National_Archives_Public_Domain",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Digitized official declassified Asian historical records under National Archives of Japan Terms.",
                                "zh": "依日本國立公文書館規範公開之戰後亞洲歷史公文檔案。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.jacar.go.jp/das/meta/{ref_code}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[JACAR] Batch query isolated failure: {e}")
                break

        logger.info(f"[JACAR] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
