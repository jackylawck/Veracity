"""
European Court of Human Rights (ECHR / HUDOC Database) Production Adapter
符合 BaseAdapter 統一時間窗口，採集歐洲最高人權司法判決、跨國秘密引渡審查與公民權利終審公文。
"""
import re
import html
import time
import logging
import requests
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
from adapters.base import BaseAdapter

logger = logging.getLogger("Veracity.Adapters.ECHR")

class EchrHudocIngestionError(Exception):
    pass

class EuropeanCourtHumanRightsProductionAdapter(BaseAdapter):
    NAME = "GLOBAL_ECHR"
    # 歐洲人權法院 HUDOC 官方公開檢索 REST API
    API_URL = "https://hudoc.echr.coe.int/app/query/results"
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
            return "Untitled European Human Rights Court Judgment"
        stripped = re.sub(r"<[^>]+>", "", raw_text)
        unescaped = html.unescape(stripped)
        return " ".join(unescaped.split()).strip()

    def _execute_with_retry(self, params: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(self.API_URL, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    backoff = 2 ** attempt
                    logger.warning(f"[ECHR] Rate limited (429). Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                if resp.status_code in (404, 502, 503):
                    logger.warning(f"[ECHR] HUDOC portal maintenance ({resp.status_code}).")
                    return {"results": []}
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise EchrHudocIngestionError(f"ECHR API unreachable: {exc}") from exc
                time.sleep(2 ** attempt)
        raise EchrHudocIngestionError("ECHR retry budget exhausted.")

    def fetch_records(self, max_pages: int = 2, page_size: int = 15) -> List[Dict[str, Any]]:
        ingested = []
        seen_ids: Set[str] = set()

        start_year, end_year = self.get_unified_date_window()
        # 歐洲人權法院於 1959 年成立，首批判決自 1960 年代展開
        echr_start = max(1959, int(start_year))
        logger.info(f"[ECHR] Applying Historical Window: {echr_start} to {end_year}")

        for page_idx in range(max_pages):
            params = {
                "query": 'contentsitename:ECHR AND (kpdate >= "' + str(echr_start) + '-01-01" AND kpdate <= "' + str(end_year) + '-12-31") AND documentcollectionid2:"JUDGMENTS"',
                "select": "itemid,appno,docname,kpdate,originatingagency",
                "sort": "kpdate asc",
                "start": str(page_idx * page_size),
                "length": str(page_size)
            }

            try:
                payload = self._execute_with_retry(params)
                results = payload.get("results", [])

                if not results:
                    break

                for doc in results:
                    columns = doc.get("columns", {})
                    item_id = str(columns.get("itemid") or "").strip()
                    if not item_id or item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    case_name = self.clean_text(columns.get("docname"))
                    app_no = columns.get("appno", f"ECHR-APP-{item_id}")
                    judgment_date = columns.get("kpdate", f"{echr_start}-{end_year}")

                    record: Dict[str, Any] = {
                        "record_id": f"echr:{item_id.replace('/', '_').replace(' ', '')}",
                        "verification_level": "metadata_only",
                        "fixity": {"hash_algorithm": "NONE", "hash_value": None, "file_size_bytes": None},
                        "archival_context": {
                            "repository": {
                                "en": "European Court of Human Rights Archives (Strasbourg, France)",
                                "zh": "歐洲人權法院檔案處 (法國史特拉斯堡)"
                            },
                            "fonds": "Council of Europe Human Rights Judicial Proceedings Fonds",
                            "series": "歐洲人權公約 (ECHR) 終審司法判決全宗",
                            "call_number": f"ECHR-CASE-{app_no}",
                            "title": {
                                "en": f"[ECHR Judgment] {case_name}",
                                "zh": None
                            },
                            "covering_dates": judgment_date[:10] if len(judgment_date) >= 10 else judgment_date
                        },
                        "heuristic_clues": {
                            "phase_2_status": "STUB_ACTIVE"
                        },
                        "rights_statement": {
                            "license_category": "Council_of_Europe_Open_Access",
                            "reuse_permitted": True,
                            "legal_disclaimer": {
                                "en": "Official judicial judgments released by the European Court of Human Rights under Council of Europe Open Access mandates.",
                                "zh": "依歐洲理事會開放近用準則公佈之歐洲人權法院法定判決，供公眾查閱與人權法證核驗。"
                            }
                        },
                        "provenance": {
                            "source_manifest_url": f"https://hudoc.echr.coe.int/eng?i={item_id}",
                            "retrieved_at_utc": datetime.now(timezone.utc).isoformat()
                        }
                    }
                    ingested.append(record)

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"[ECHR] Batch isolated failure: {e}")
                break

        logger.info(f"[ECHR] Pipeline successfully acquired {len(ingested)} distinct records.")
        return ingested
