"""应用指标：请求耗时、LLM 调用、错误计数（内存存储）"""
import time
import threading
from collections import defaultdict


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._reset()

    def _reset(self):
        self.chat_total = 0
        self.chat_errors = 0
        self.chat_durations: list[float] = []       # 最近 100 次耗时
        self.upload_total = 0
        self.llm_calls = 0
        self.llm_errors = 0
        self.llm_total_duration = 0.0
        self.rate_limited = 0

    # ── 记录 ──
    def record_chat(self, duration: float, error: bool = False):
        with self._lock:
            self.chat_total += 1
            if error:
                self.chat_errors += 1
            self.chat_durations.append(duration)
            if len(self.chat_durations) > 100:
                self.chat_durations = self.chat_durations[-100:]

    def record_upload(self):
        with self._lock:
            self.upload_total += 1

    def record_llm(self, duration: float, error: bool = False):
        with self._lock:
            self.llm_calls += 1
            if error:
                self.llm_errors += 1
            self.llm_total_duration += duration

    def record_rate_limited(self):
        with self._lock:
            self.rate_limited += 1

    # ── 查询 ──
    def snapshot(self) -> dict:
        with self._lock:
            durs = self.chat_durations
            return {
                "chat": {
                    "total": self.chat_total,
                    "errors": self.chat_errors,
                    "error_rate": round(self.chat_errors / max(self.chat_total, 1), 3),
                    "avg_duration_ms": round(sum(durs) / max(len(durs), 1) * 1000, 1),
                    "p95_duration_ms": round(sorted(durs)[int(len(durs) * 0.95)] * 1000, 1) if len(durs) >= 20 else None,
                },
                "upload": {"total": self.upload_total},
                "llm": {
                    "calls": self.llm_calls,
                    "errors": self.llm_errors,
                    "error_rate": round(self.llm_errors / max(self.llm_calls, 1), 3),
                    "avg_duration_ms": round(self.llm_total_duration / max(self.llm_calls, 1) * 1000, 1),
                },
                "rate_limited": self.rate_limited,
            }


metrics = Metrics()
