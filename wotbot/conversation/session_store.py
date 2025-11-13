from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class Message:
    role: str
    content: str
    timestamp: float = field(default_factory=lambda: time.time())


@dataclass
class Session:
    user_id: str
    messages: List[Message] = field(default_factory=list)
    developer_mode: bool = False
    memory: Dict[str, str] = field(default_factory=dict)


class SessionStore:
    def __init__(self):
        self._store: Dict[str, Session] = {}

    def get(self, user_id: str) -> Session:
        if user_id not in self._store:
            self._store[user_id] = Session(user_id=user_id)
        return self._store[user_id]

    def append(self, user_id: str, role: str, content: str):
        s = self.get(user_id)
        s.messages.append(Message(role=role, content=content))
        # Trim history to last N messages to control context size
        if len(s.messages) > 40:
            s.messages = s.messages[-40:]

    def set_developer_mode(self, user_id: str, value: bool):
        s = self.get(user_id)
        s.developer_mode = value

    def get_developer_mode(self, user_id: str) -> bool:
        return self.get(user_id).developer_mode

    def set_memory(self, user_id: str, key: str, value: str):
        s = self.get(user_id)
        s.memory[key] = value

    def get_memory(self, user_id: str, key: str) -> Optional[str]:
        return self.get(user_id).memory.get(key)

