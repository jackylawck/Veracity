cat << 'EOF' > scripts/circuit_breaker.py
"""
The Veracity // Statistical Rolling Anomaly Guard
自適應滑動視窗統計斷路器：以真實淨變異量（Mutations / Net Additions）為訊號源。
（具備冷啟動樣本擴建防護、固定滑動視窗切片、除零保護與雙重閾值防誤觸機制）
"""
import math
from typing import List, Dict, Any, Optional


class RollingAnomalyGuard:
    def __init__(
        self,
        mutation_history: Optional[List[Any]] = None,
        window_size: int = 14,
        z_threshold: float = 2.5,
        min_absolute_threshold: int = 50,
        bootstrap_runs: int = 5
    ):
        """
        :param mutation_history: 歷史變異數陣列（支援 None、float、整數清洗）
        :param window_size: 滾動視窗大小（預設取最近 14 次運行）
        :param z_threshold: 標準差倍數閾值（預設 2.5σ）
        :param min_absolute_threshold: 絕對變更底線（預設 50 筆；適用於每日批次，若改為高頻採集應調降）
        :param bootstrap_runs: 樣本積累期門檻（低於 5 次運行時不啟動阻斷）
        """
        cleaned: List[int] = []
        for x in (mutation_history or []):
            try:
                # 浮點數四捨五入後轉整數，字串整數安全轉換
                cleaned.append(int(round(float(x))))
            except (ValueError, TypeError):
                continue

        self.history = cleaned
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.min_absolute_threshold = min_absolute_threshold
        self.bootstrap_runs = bootstrap_runs

    def evaluate(
        self,
        current_mutations: Optional[int] = None,
        current_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        評估本次變異量是否偏離統計常態。
        兼容位置引數與 current_mutations / current_count 命名引數。
        """
        val = current_mutations if current_mutations is not None else current_count
        if val is None:
            val = 0
        else:
            try:
                val = max(0, int(round(float(val))))
            except (ValueError, TypeError):
                val = 0

        # 1. 樣本擴建期 (Bootstrap Phase) 放行（補齊量化指標為 None 以維持回傳契約一致性）
        if len(self.history) < self.bootstrap_runs:
            return {
                "is_anomaly": False,
                "severity": "NORMAL",
                "status": "BOOTSTRAP_PHASE",
                "reason": "BOOTSTRAP_PHASE",
                "detail": f"Baseline accumulating: ({len(self.history)}/{self.bootstrap_runs} runs recorded).",
                "current": val,
                "sample_count": len(self.history),
                "mean": None,
                "std_dev": None,
                "z_score": None,
                "threshold": None
            }

        # 2. 滑動視窗切片（只取最近 N 次，避免歷史基線無限累積鈍化）
        recent_window = self.history[-self.window_size:]
        n = len(recent_window)
        mean = sum(recent_window) / n
        variance = sum((x - mean) ** 2 for x in recent_window) / n
        std_dev = math.sqrt(variance)

        # 3. 穩定標準差底線防護（除零保護）
        effective_std = std_dev if std_dev > 1e-6 else 1.0

        # 4. 統計指標與判定上限計算（全面對齊 effective_std）
        z_score = (val - mean) / effective_std
        upper_bound = mean + (self.z_threshold * effective_std)

        # 5. 雙重門檻判定：統計偏離 + 突破絕對底線
        is_stat_anomaly = val > upper_bound
        is_significant_surge = val > self.min_absolute_threshold

        if is_stat_anomaly and is_significant_surge:
            severity = "CRITICAL" if z_score > (self.z_threshold + 1.0) else "WARNING"
            return {
                "is_anomaly": True,
                "severity": severity,
                "status": "TRIPPED",
                "reason": "STATISTICAL_ANOMALY_DETECTED",
                "action": "HALT_PIPELINE",
                "detail": f"Anomalous surge: {val} items (Baseline: {mean:.1f} ± {std_dev:.1f}, Z: {z_score:.2f})",
                "current": val,
                "sample_count": n,
                "mean": round(mean, 2),
                "std_dev": round(std_dev, 2),
                "z_score": round(z_score, 2),
                "threshold": round(upper_bound, 2)
            }

        return {
            "is_anomaly": False,
            "severity": "NORMAL",
            "status": "HEALTHY",
            "reason": "WITHIN_STATISTICAL_TOLERANCE",
            "detail": f"Mutations ({val}) within statistical tolerance (Mean: {mean:.1f}, Z: {z_score:.2f}).",
            "current": val,
            "sample_count": n,
            "mean": round(mean, 2),
            "std_dev": round(std_dev, 2),
            "z_score": round(z_score, 2),
            "threshold": round(upper_bound, 2)
        }
EOF
