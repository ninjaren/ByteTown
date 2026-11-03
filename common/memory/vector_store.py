"""語意記憶：把對話內容嵌入成向量存起來，之後可以用語意搜尋「回憶」相關內容，
不像關鍵字比對只能找到字面完全符合的東西。

移植自 qwen3_4b/rag.py，差異：
- 不寫死 chroma_db 路徑，建構時傳入 persist_dir
- 不寫死用 Ollama 的 embedding，改成注入 Embedder（介面見 embedder.py）
- 多了 metadata 跟 distance（相似度）方便呼叫方判斷找到的記憶有多相關
"""
from pathlib import Path
from typing import Optional, Union

from .embedder import Embedder


class VectorMemory:
    def __init__(self, persist_dir: Union[str, Path], collection_name: str, embedder: Embedder):
        import chromadb  # 延遲匯入：沒裝 chromadb 但用不到語意記憶時不會報錯

        self._embedder = embedder
        self._client = chromadb.PersistentClient(path=str(Path(persist_dir)))
        self._collection_name = collection_name
        self._col = self._client.get_or_create_collection(collection_name)

    def remember(self, memory_id: str, text: str, metadata: Optional[dict] = None) -> bool:
        # 把一段文字嵌入並存進向量資料庫；用 upsert 避免同 id 重複儲存
        # embedding 服務未就緒時靜默回傳 False，不中斷呼叫方的主流程
        vec = self._embedder.embed(text)
        if vec is None:
            return False
        self._col.upsert(ids=[memory_id], documents=[text], embeddings=[vec], metadatas=[metadata or {}])
        return True

    def recall(self, query: str, top_k: int = 3) -> list[dict]:
        # 用語意搜尋找出跟 query 最相關的過去記憶，回傳 [{"text","metadata","distance"}, ...]
        count = self._col.count()
        if count == 0:
            return []
        vec = self._embedder.embed(query)
        if vec is None:
            return []
        results = self._col.query(query_embeddings=[vec], n_results=min(top_k, count))
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = (results.get("distances") or [[None] * len(docs)])[0]
        return [{"text": d, "metadata": m, "distance": dist} for d, m, dist in zip(docs, metas, dists)]

    def forget_all(self) -> None:
        # 清空所有記憶（刪除並重建 collection），主要用於測試或重置
        self._client.delete_collection(self._collection_name)
        self._col = self._client.get_or_create_collection(self._collection_name)
