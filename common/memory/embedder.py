"""Embedding 介面：把文字轉成向量，用於語意搜尋。

跟 LLMProvider 一樣做成可替換的介面——目前只有 Ollama 的實作
（nomic-embed-text），之後要換成 OpenAI/Anthropic 的 embedding API，
只要照這個介面多寫一個 provider class，上層 VectorMemory 完全不用改。
"""
from abc import ABC, abstractmethod
from typing import Optional


class Embedder(ABC):
    @abstractmethod
    def embed(self, text: str) -> Optional[list[float]]:
        """把文字轉成向量；嵌入服務未就緒或失敗時回傳 None，
        呼叫方應該跳過這次語意記憶，而不是讓整個 agent 流程中斷。
        """


class OllamaEmbedder(Embedder):
    def __init__(self, model: str = "nomic-embed-text", host: str = "http://localhost:11434"):
        self._model = model
        self._host = host.rstrip("/")

    def embed(self, text: str) -> Optional[list[float]]:
        import requests

        try:
            resp = requests.post(
                f"{self._host}/api/embed",
                json={"model": self._model, "input": text},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["embeddings"][0]
        except Exception:
            return None
