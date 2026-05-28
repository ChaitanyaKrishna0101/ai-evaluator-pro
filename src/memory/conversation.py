"""Sliding-window conversation memory – keeps last N turns."""
from collections import deque
from typing import List, Dict

class ConversationMemory:
    def __init__(self, window: int = 10):
        self.window = window
        self._history: deque = deque(maxlen=window * 2)  # user+assistant pairs

    def add(self, role: str, content: str):
        self._history.append({"role": role, "content": content})

    def get_history(self) -> List[Dict[str, str]]:
        return list(self._history)

    def build_context(self) -> str:
        return "\n".join(f"{m['role'].upper()}: {m['content']}" for m in self._history)

    def clear(self):
        self._history.clear()

    def to_list(self) -> List[Dict[str, str]]:
        return list(self._history)
