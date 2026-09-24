"""
Base Adapter Interface
定義全域統一的時間窗口基準與介面契約。
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple
from datetime import datetime, timezone

class BaseAdapter(ABC):
    NAME: str = "BASE_ADAPTER"

    # 全域統一基準：1945 年（二戰結束 / 現代解密公文與情報體系起點）
    DEFAULT_START_DATE: str = "1945-01-01"

    # 國際法定解密年限基準（以 30 年法則為核心）
    STATUTORY_RULE_YEARS: int = 30

    @classmethod
    def get_unified_date_window(cls) -> Tuple[str, str]:
        """
        全域時間窗口計算器：
        起始：統一為 1945-01-01
        截止：當前年份扣除法定解密年限（例如 2026 年執行時，截止為 1996-12-31）
        """
        current_year = datetime.now(timezone.utc).year
        statutory_end_year = current_year - cls.STATUTORY_RULE_YEARS
        end_date = f"{statutory_end_year}-12-31"
        return cls.DEFAULT_START_DATE, end_date

    @abstractmethod
    def fetch_records(self) -> List[Dict[str, Any]]:
        """採集並回傳符合 schemas/record.schema.json 的檔案清單。"""
        pass
