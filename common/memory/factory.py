"""建立預設的記憶元件（session 存檔 + 語意向量庫），
讓 agent_runner / delegate_tool 不用各自重複一樣的建構邏輯。

所有 agent 預設共用同一個 collection（byte_town_history），
這樣 Moss 才能查到「全鎮」的歷史，不是只有自己那份。
"""
from pathlib import Path
from typing import Union

from .embedder import OllamaEmbedder
from .session_store import SessionStore
from .vector_store import VectorMemory


def build_default_memory(memory_dir: Union[str, Path]) -> tuple[SessionStore, VectorMemory]:
    memory_dir = Path(memory_dir)
    session_store = SessionStore(memory_dir / "sessions")
    vector_memory = VectorMemory(memory_dir / "chroma", collection_name="byte_town_history", embedder=OllamaEmbedder())
    return session_store, vector_memory
