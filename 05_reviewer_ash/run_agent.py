"""Ash（審核者）的執行入口。

執行： python 05_reviewer_ash/run_agent.py "審查一下 workspace/hello.py"
"""
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = AGENT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from common.agent_runner import run_agent_cli
from common.tools.builtin import ReadFileTool, ListFilesTool, WorkspaceGuard

DATA_DIR = ROOT_DIR / "data"
GUARD = WorkspaceGuard(DATA_DIR / "workspace")

if __name__ == "__main__":
    run_agent_cli(
        AGENT_DIR,
        agent_name="Ash",
        tool_instances=[ReadFileTool(GUARD), ListFilesTool(GUARD)],
        system_prompt="你是 Ash，byte_town 的審核者 agent。回答一律使用繁體中文。",
        default_task="審查一下 workspace 底下的 hello.py",
        memory_dir=DATA_DIR / "memory",
    )
