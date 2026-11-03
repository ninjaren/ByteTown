"""Bolt（程式開發者）的執行入口。

執行： python 03_coder_bolt/run_agent.py "在 workspace 建立 hello.py，印出 Hello byte_town"
"""
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = AGENT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from common.agent_runner import run_agent_cli
from common.tools.builtin import ListFilesTool, ReadFileTool, WriteFileTool, AppendFileTool, CalculatorTool, WorkspaceGuard

DATA_DIR = ROOT_DIR / "data"
# Bolt 只能在共用的 workspace 底下動檔案，不會碰到 byte_town 自己的框架原始碼
GUARD = WorkspaceGuard(DATA_DIR / "workspace")

if __name__ == "__main__":
    run_agent_cli(
        AGENT_DIR,
        agent_name="Bolt",
        tool_instances=[
            ListFilesTool(GUARD), ReadFileTool(GUARD), WriteFileTool(GUARD),
            AppendFileTool(GUARD), CalculatorTool(),
        ],
        system_prompt="你是 Bolt，byte_town 的程式開發者 agent。回答一律使用繁體中文。",
        default_task="在 workspace 建立 hello.py，內容印出 Hello byte_town",
        memory_dir=DATA_DIR / "memory",
    )
