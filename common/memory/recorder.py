"""把一次 agentic loop 的結果同時寫進 session 存檔跟語意記憶庫。

這是 run_agent_cli（CLI 入口）跟 DelegateToAgentTool（委派入口）共用的收尾動作，
避免兩處各自重複一份「存檔 + embedding」的邏輯。任何一步失敗都不該讓主流程掛掉，
所以內部已經把失敗都吞掉（session 寫檔失敗才會真的拋錯，embedding 失敗只是靜默跳過）。
"""
from datetime import datetime
from typing import Optional

from .session_store import SessionStore
from .vector_store import VectorMemory


def record_turn(
    agent_name: str,
    task: str,
    result,  # AgentLoopResult，型別不在這裡 import 是為了避免 common.memory <-> common.agent 循環依賴
    session_store: Optional[SessionStore] = None,
    vector_memory: Optional[VectorMemory] = None,
) -> Optional[str]:
    session_id = None
    created_at = datetime.now().isoformat(timespec="seconds")

    if session_store is not None:
        session_id = session_store.save_turn(
            agent_name=agent_name,
            task=task,
            answer=result.text,
            messages=result.messages,
            tool_log=result.tool_log,
            created_at=created_at,
        )

    if vector_memory is not None:
        memory_id = session_id or f"{agent_name}_{abs(hash(task + result.text))}"
        vector_memory.remember(
            memory_id=memory_id,
            text=f"任務：{task}\n回答：{result.text}",
            metadata={"agent": agent_name, "task": task, "created_at": created_at},
        )

    return session_id
