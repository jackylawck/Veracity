"""
Rolling Statistical Anomaly Guard
自適應滾動斷路器：以真實淨變更量（Mutations / Net Additions）為訊號源。
"""
import math
from typing import List, Dict, Any

class RollingAnomalyGuard:
    def __init__(self, mutation_history: List[int]):
        self.history = [int(x) for x in mutation_history if isinstance(x, (int, float))]

    def evaluate(self, current_mutations: int) -> Dict[str, Any]:
        if len(self.history) < 5:
            return {
                "is_anomaly": False,
                "reason": "BOOTSTRAP_PHASE",
                "detail": f"Baseline accumulating: ({len(self.history)}/5 runs recorded)."
            }

        n = len(self.history)
        mean = sum(self.history) / n
        variance = sum((x - mean) ** 2 for x in self.history) / n
        std_dev = math.sqrt(variance)

        upper_bound = mean + 2.5 * std_dev

        if current_mutations > upper_bound and current_mutations > 50:
            return {
                "is_anomaly": True,
                "severity": "CRITICAL",
                "action": "HALT_PIPELINE",
                "detail": f"Anomalous surge in mutations: {current_mutations} new items (Baseline: {mean:.1f} ± {std_dev:.1f})"
            }

        return {
            "is_anomaly": False,
            "reason": "WITHIN_STATISTICAL_TOLERANCE",
            "detail": f"Mutations ({current_mutations}) within statistical variance."
        }
