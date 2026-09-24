"""
Base Adapter Interface
所有官方檔案館適配器必須遵守的抽象介面契約。
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseAdapter(ABC):
    NAME: str = "BASE_ADAPTER"

    @abstractmethod
    def fetch_records(self) -> List[Dict[str, Any]]:
        """採集並回傳符合 schemas/record.schema.json 的檔案清單。"""
        pass
