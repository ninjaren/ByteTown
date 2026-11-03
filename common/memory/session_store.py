"""Session 存檔：把每次 agentic loop 的完整對話紀錄存成 JSON，之後可以回頭查。

移植自 qwen3_4b/session_manager.py，差異：
- 不寫死 SESSIONS_DIR，建構時傳入
- 每個 session 額外存 agent 名稱、原始任務、工具呼叫紀錄等結構化資訊，
  方便之後統計「誰被委派最多次」或直接還原某次任務的完整經過
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


class SessionStore:
    def __init__(self, sessions_dir: Union[str, Path]):
        self._dir = Path(sessions_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._meta_file = self._dir / "_meta.json"

    def _load_meta(self) -> dict:
        # 所有 session 的 metadata 集中存這個檔案，列清單時只讀這一個小檔，不用載入全部對話紀錄
        if self._meta_file.exists():
            try:
                return json.loads(self._meta_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_meta(self, meta: dict) -> None:
        self._meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _session_file(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def save_turn(
        self,
        agent_name: str,
        task: str,
        answer: str,
        messages: list,
        tool_log: list,
        created_at: Optional[str] = None,
    ) -> str:
        # 存一輪完整的 agentic loop 結果；session_id 自動產生，每個 session 一個獨立 JSON 檔
        session_id = f"{agent_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        created_at = created_at or datetime.now().isoformat(timespec="seconds")
        record = {
            "session_id": session_id,
            "agent": agent_name,
            "task": task,
            "answer": answer,
            "messages": messages,
            "tool_log": [[name, args, text] for name, args, text in tool_log],
            "created_at": created_at,
        }
        self._session_file(session_id).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        meta = self._load_meta()
        meta[session_id] = {"agent": agent_name, "task": task, "created_at": created_at}
        self._save_meta(meta)
        return session_id

    def load(self, session_id: str) -> Optional[dict]:
        f = self._session_file(session_id)
        if not f.exists():
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_sessions(self, agent_name: Optional[str] = None, limit: Optional[int] = None) -> list[dict]:
        # 依建立時間新到舊排序，方便瀏覽「最近發生的事」
        meta = self._load_meta()
        items = [{"session_id": sid, **info} for sid, info in meta.items()]
        if agent_name:
            items = [i for i in items if i.get("agent") == agent_name]
        items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
        return items[:limit] if limit else items
