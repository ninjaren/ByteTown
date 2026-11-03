"""Quill（寫手）的執行入口。

執行： python 04_writer_quill/run_agent.py "把 workspace/hello.py 的內容寫成一份簡短說明文件"
"""
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = AGENT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from common.agent_runner import run_agent_cli
from common.tools.builtin import ReadFileTool, WriteFileTool, AppendFileTool, WorkspaceGuard

DATA_DIR = ROOT_DIR / "data"
GUARD = WorkspaceGuard(DATA_DIR / "workspace")

if __name__ == "__main__":
    run_agent_cli(
        AGENT_DIR,
        agent_name="Quill",
        tool_instances=[ReadFileTool(GUARD), WriteFileTool(GUARD), AppendFileTool(GUARD)],
        system_prompt="你是 Quill，byte_town 的寫手 agent。回答一律使用繁體中文。",
        default_task="把 workspace 底下的 hello.py 內容整理成一份簡短的說明文件，存成 hello_report.md",
        memory_dir=DATA_DIR / "memory",
    )
