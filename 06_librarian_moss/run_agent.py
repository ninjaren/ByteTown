"""Moss（圖書館員）的執行入口。

Moss 是全 byte_town 共用記憶的單一查詢入口：多出 recall_memory（語意搜尋過去
任務與回答）跟 list_recent_sessions（依時間瀏覽歷史），底層接的是 common/memory
裡所有 agent 共用的同一份 session 存檔跟向量資料庫。

執行： python 06_librarian_moss/run_agent.py "看看 data 底下有哪些檔案"
"""
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = AGENT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from common.agent_runner import run_agent_cli
from common.memory import build_default_memory
from common.tools.builtin import (
    ListFilesTool, ReadFileTool, WriteFileTool, AppendFileTool,
    DeleteFileTool, ReadCsvTool, MoveFileTool, SplitPdfTool, WorkspaceGuard,
    RecallMemoryTool, ListRecentSessionsTool,
)

DATA_DIR = ROOT_DIR / "data"
# Moss 是圖書館員，權限範圍比其他人廣：整個 data/ 目錄（workspace、charts、github_trending 都看得到）
GUARD = WorkspaceGuard(DATA_DIR)

SESSION_STORE, VECTOR_MEMORY = build_default_memory(DATA_DIR / "memory")

if __name__ == "__main__":
    run_agent_cli(
        AGENT_DIR,
        agent_name="Moss",
        tool_instances=[
            ListFilesTool(GUARD), ReadFileTool(GUARD), WriteFileTool(GUARD), AppendFileTool(GUARD),
            DeleteFileTool(GUARD), ReadCsvTool(GUARD), MoveFileTool(GUARD), SplitPdfTool(GUARD),
            RecallMemoryTool(VECTOR_MEMORY), ListRecentSessionsTool(SESSION_STORE),
        ],
        system_prompt="你是 Moss，byte_town 的圖書館員 agent。回答一律使用繁體中文。",
        default_task="看看 data 底下有哪些檔案與資料夾",
        memory_dir=DATA_DIR / "memory",
    )
