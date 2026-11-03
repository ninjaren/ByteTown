"""讓 agent 可以查詢 byte_town 共用記憶的工具，底層是 common/memory 的
VectorMemory（語意搜尋）跟 SessionStore（精確瀏覽歷史）。

設計上這兩個工具只接給 Moss（圖書館員）：Moss 是全 byte_town 共用知識的
單一來源，其他 agent 想知道「之前有沒有人問過類似的事」，應該委派給 Moss
去查，而不是每個 agent 各自接一份記憶工具——這樣記憶的查詢入口才統一。
"""
from ..base import Tool, ToolResult
from ...memory.session_store import SessionStore
from ...memory.vector_store import VectorMemory


class RecallMemoryTool(Tool):
    # terminal：直接把搜尋結果當最終答案回傳，不讓模型重新敘述——
    # 已經實測過，小模型轉述語意搜尋結果時會「順手」捏造真實不存在的額外記錄
    terminal = True
    name = "recall_memory"
    description = (
        "用語意搜尋查詢 byte_town 過去處理過的任務與回答，"
        "適合回答「之前有沒有人問過類似的事」「上次查到的結果是什麼」"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "想查詢的內容，用自然語言描述即可，不需要跟原始問題字面相同"},
            "top_k": {"type": "integer", "description": "最多回傳幾筆，預設 3"},
        },
        "required": ["query"],
    }

    def __init__(self, memory: VectorMemory):
        self._memory = memory

    def run(self, query: str, top_k: int = 3, **kwargs) -> ToolResult:
        memories = self._memory.recall(query, top_k=top_k)
        if not memories:
            return ToolResult(output="沒有找到相關的過去記錄")
        lines = []
        for i, m in enumerate(memories, 1):
            meta = m.get("metadata") or {}
            lines.append(f"[{i}] ({meta.get('agent', '?')} / {meta.get('created_at', '?')})\n{m['text']}")
        return ToolResult(output="\n\n".join(lines))


class ListRecentSessionsTool(Tool):
    terminal = True  # 同樣是資料查詢類工具，原因見 RecallMemoryTool
    name = "list_recent_sessions"
    description = "依時間列出 byte_town 最近處理過的任務紀錄，適合瀏覽歷史而不是語意搜尋"
    parameters = {
        "type": "object",
        "properties": {
            "agent": {"type": "string", "description": "只看某個 agent 的紀錄（例如 Owl），留空看全部"},
            "limit": {"type": "integer", "description": "最多列出幾筆，預設 10"},
        },
    }

    def __init__(self, session_store: SessionStore):
        self._store = session_store

    def run(self, agent: str = "", limit: int = 10, **kwargs) -> ToolResult:
        items = self._store.list_sessions(agent_name=agent or None, limit=limit)
        if not items:
            return ToolResult(output="沒有歷史紀錄")
        lines = [f"- [{i['created_at']}] {i['agent']}：{i['task']}" for i in items]
        return ToolResult(output="\n".join(lines))
