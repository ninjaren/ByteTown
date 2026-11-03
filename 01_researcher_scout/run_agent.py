"""Scout（研究者）的執行入口。

執行： python 01_researcher_scout/run_agent.py "byte_town 多代理人系統設計"
"""
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = AGENT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from common.agent_runner import run_agent_cli
from common.tools.builtin import (
    SearchWebTool, BrowseUrlTool, FetchRssTool, ExtractLinksTool,
    ReadPdfTool, ReadPdfPageTool, SplitPdfTool, GithubTrendingTool, WorkspaceGuard,
)

DATA_DIR = ROOT_DIR / "data"
GUARD = WorkspaceGuard(DATA_DIR / "workspace")  # 讀 PDF 用，範圍限制在共用 workspace

if __name__ == "__main__":
    run_agent_cli(
        AGENT_DIR,
        agent_name="Scout",
        tool_instances=[
            SearchWebTool(), BrowseUrlTool(), FetchRssTool(), ExtractLinksTool(),
            ReadPdfTool(GUARD), ReadPdfPageTool(GUARD), SplitPdfTool(GUARD),
            GithubTrendingTool(state_dir=DATA_DIR / "github_trending"),
        ],
        system_prompt="你是 Scout，byte_town 的研究者 agent。回答一律使用繁體中文。",
        default_task="byte_town 多代理人系統設計",
        memory_dir=DATA_DIR / "memory",
    )
