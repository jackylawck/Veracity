"""
Hong Kong Public Records Office (HK PRO) Production Adapter
落實香港歷史檔案館 (HKRS 系統) 戰後解密公文之法證級全宗存證。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.HKPRO")

class HkProIngestionError(Exception):
    pass

class HkProProductionAdapter(BaseAdapter):
    NAME = "HK_PRO"
    # 香港政府檔案處公共查詢檢索端點
    SEARCH_URL = "https://www.grs.gov.hk/ws/search/carl/query"
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
            return "未命名法定移交案卷 (Untitled Official Record)"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.post(self.SEARCH_URL, json=payload, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[HK_PRO] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    # 若本地伺服器臨時處於非營業時間維護，記錄警告並安全降級
                    logger.warning(f"[HK_PRO] Service gateway offline ({resp.status_code}).")
                    return {"items": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise HkProIngestionError(f"HK PRO API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise HkProIngestionError("HK PRO retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_refs: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        logger.info(f"[HK_PRO] Applying Unified Historical Window: {start_year} to {end_year}")

        for page_idx in range(max_pages):
            query_payload = {
                "query": "Post-war Administration Security",
                "startYear": int(start_year),
                "endYear": int(end_year),
                "page": page_idx + 1,
                "pageSize": page_size
            }

            try:
                data = self._execute_with_retry(query_payload)
                items = data.get("items", [])

                if not items:
                    # 本地端點若處於維護窗口，以備援防禦機制回退，不阻斷其他全球適配器
                    break

                for doc in items:
                    ref_code = doc.get("hkrsRefCode") or doc.get("archiveRef")
                    if not ref_code or ref_code in seen_refs:
                        continue
                    seen_refs.add(ref_code)

                    en_title = self.clean_text(doc.get("titleEn"))
                    zh_title = self.clean_text(doc.get("titleTc")) if doc.get("titleTc") else None

                    # HKRS 全宗拆解（例如 HKRS156 屬於布政司署機密檔案）
                    fonds_match = re.match(r"(HKRS\d+)", ref_code)
                    fonds_name = fonds_match.group(1) if fonds_match else "HKRS"

                    record: Dict[str, Any] = {
                        "record_id": f"hkpro:{ref_code.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "Hong Kong Public Records Office (Kwun Tong)",
                                "zh": "香港歷史檔案館 (觀塘)"
                            },
                            "fonds": fonds_name,
                            "series": fonds_name,
                            "call_number": ref_code,
                            "title": {
                                "en": en_title,
                                "zh": zh_title
                            },
                            "covering_dates": doc.get("coveringDates", f"{start_year}-{end_year}")
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "HK_Crown_Copyright_Historical",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Archival accession by HKSAR Government Records Service for research and private study.",
                                "zh": "香港特區政府檔案處公開閱覽公文，依法律提供歷史研究與公眾查閱。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://www.grs.gov.hk/carl/recordDetails?ref={ref_code}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[HK_PRO] Pipeline batch failed gracefully: {e}")
                break

        logger.info(f"[HK_PRO] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
