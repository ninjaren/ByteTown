"""Pip（管理者）的執行入口。

這一版 Pip 真的能把子任務委派給其他 agent 執行（透過 ask_scout / ask_owl /
ask_bolt / ask_quill / ask_ash / ask_moss 這些「委派工具」，見
common/tools/builtin/delegate_tool.py），不是只用文字描述分配方案；
任務跨多個角色時，Pip 會依序呼叫對應工具，把前一個 agent 的回覆接續
委派給下一個 agent，這就是「多 agent 串接」。

執行： python 00_manager_pip/run_agent.py "幫我查一下台積電股價，再寫成一份簡短報告"
"""
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = AGENT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from common.agent_runner import run_agent_cli
from common.llm import create_llm_from_config
from common.memory import build_default_memory
from common.skills import SkillRegistry
from common.tools import ToolRegistry
from common.tools.builtin import (
    CurrentTimeTool, WorkspaceGuard, make_delegate_tool,
    SearchWebTool, BrowseUrlTool, FetchRssTool, ExtractLinksTool,
    ReadPdfTool, ReadPdfPageTool, SplitPdfTool, GithubTrendingTool,
    StockPriceTool, MarketIndexTool, MultiStockTool,
    CryptoPriceTool, MultiCryptoTool, ExchangeRateTool, CalculatorTool, StockChartTool,
    ListFilesTool, ReadFileTool, WriteFileTool, AppendFileTool,
    DeleteFileTool, ReadCsvTool, MoveFileTool,
    RecallMemoryTool, ListRecentSessionsTool,
)

DATA_DIR = ROOT_DIR / "data"
MEMORY_DIR = DATA_DIR / "memory"
WORKSPACE_GUARD = WorkspaceGuard(DATA_DIR / "workspace")
BROAD_GUARD = WorkspaceGuard(DATA_DIR)


# 每個 _build_xxx() 都跟對應 agent 自己 run_agent.py 裡的工具/skill 設定一致，
# 只是這裡回傳給 DelegateToAgentTool 延遲呼叫，不是直接跑迴圈。
def _build_scout():
    agent_dir = ROOT_DIR / "01_researcher_scout"
    llm = create_llm_from_config(agent_dir / "config.yaml")
    tools = ToolRegistry()
    for t in (
        SearchWebTool(), BrowseUrlTool(), FetchRssTool(), ExtractLinksTool(),
        ReadPdfTool(WORKSPACE_GUARD), ReadPdfPageTool(WORKSPACE_GUARD), SplitPdfTool(WORKSPACE_GUARD),
        GithubTrendingTool(state_dir=DATA_DIR / "github_trending"),
    ):
        tools.register(t)
    skills = SkillRegistry()
    skills.load_dir(agent_dir / "skills")
    return llm, tools, skills, "你是 Scout，byte_town 的研究者 agent。回答一律使用繁體中文。"


def _build_owl():
    agent_dir = ROOT_DIR / "02_analyst_owl"
    llm = create_llm_from_config(agent_dir / "config.yaml")
    tools = ToolRegistry()
    for t in (
        StockPriceTool(), MarketIndexTool(), MultiStockTool(),
        CryptoPriceTool(), MultiCryptoTool(), ExchangeRateTool(),
        CalculatorTool(), StockChartTool(output_dir=DATA_DIR / "charts"),
    ):
        tools.register(t)
    skills = SkillRegistry()
    skills.load_dir(agent_dir / "skills")
    return llm, tools, skills, "你是 Owl，byte_town 的分析師 agent。回答一律使用繁體中文。"


def _build_bolt():
    agent_dir = ROOT_DIR / "03_coder_bolt"
    llm = create_llm_from_config(agent_dir / "config.yaml")
    tools = ToolRegistry()
    for t in (
        ListFilesTool(WORKSPACE_GUARD), ReadFileTool(WORKSPACE_GUARD), WriteFileTool(WORKSPACE_GUARD),
        AppendFileTool(WORKSPACE_GUARD), CalculatorTool(),
    ):
        tools.register(t)
    skills = SkillRegistry()
    skills.load_dir(agent_dir / "skills")
    return llm, tools, skills, "你是 Bolt，byte_town 的程式開發者 agent。回答一律使用繁體中文。"


def _build_quill():
    agent_dir = ROOT_DIR / "04_writer_quill"
    llm = create_llm_from_config(agent_dir / "config.yaml")
    tools = ToolRegistry()
    for t in (ReadFileTool(WORKSPACE_GUARD), WriteFileTool(WORKSPACE_GUARD), AppendFileTool(WORKSPACE_GUARD)):
        tools.register(t)
    skills = SkillRegistry()
    skills.load_dir(agent_dir / "skills")
    return llm, tools, skills, "你是 Quill，byte_town 的寫手 agent。回答一律使用繁體中文。"


def _build_ash():
    agent_dir = ROOT_DIR / "05_reviewer_ash"
    llm = create_llm_from_config(agent_dir / "config.yaml")
    tools = ToolRegistry()
    for t in (ReadFileTool(WORKSPACE_GUARD), ListFilesTool(WORKSPACE_GUARD)):
        tools.register(t)
    skills = SkillRegistry()
    skills.load_dir(agent_dir / "skills")
    return llm, tools, skills, "你是 Ash，byte_town 的審核者 agent。回答一律使用繁體中文。"


def _build_moss():
    agent_dir = ROOT_DIR / "06_librarian_moss"
    llm = create_llm_from_config(agent_dir / "config.yaml")
    tools = ToolRegistry()
    session_store, vector_memory = build_default_memory(MEMORY_DIR)
    for t in (
        ListFilesTool(BROAD_GUARD), ReadFileTool(BROAD_GUARD), WriteFileTool(BROAD_GUARD), AppendFileTool(BROAD_GUARD),
        DeleteFileTool(BROAD_GUARD), ReadCsvTool(BROAD_GUARD), MoveFileTool(BROAD_GUARD), SplitPdfTool(BROAD_GUARD),
        RecallMemoryTool(vector_memory), ListRecentSessionsTool(session_store),
    ):
        tools.register(t)
    skills = SkillRegistry()
    skills.load_dir(agent_dir / "skills")
    return llm, tools, skills, "你是 Moss，byte_town 的圖書館員 agent。回答一律使用繁體中文。"


if __name__ == "__main__":
    pip_tools = [
        CurrentTimeTool(),
        make_delegate_tool("scout", "Scout（研究者）", "需要上網查資料、讀文章時，把子任務委派給 Scout", _build_scout, memory_dir=MEMORY_DIR),
        make_delegate_tool("owl", "Owl（分析師）", "需要查股票/虛擬貨幣/做數值分析時，把子任務委派給 Owl", _build_owl, memory_dir=MEMORY_DIR),
        make_delegate_tool("bolt", "Bolt（程式開發者）", "需要寫或修改程式碼時，把子任務委派給 Bolt", _build_bolt, memory_dir=MEMORY_DIR),
        make_delegate_tool("quill", "Quill（寫手）", "需要整理成報告或文件時，把子任務委派給 Quill", _build_quill, memory_dir=MEMORY_DIR),
        make_delegate_tool("ash", "Ash（審核者）", "需要審查程式碼或文件品質時，把子任務委派給 Ash", _build_ash, memory_dir=MEMORY_DIR),
        make_delegate_tool(
            "moss", "Moss（圖書館員）",
            "需要歸檔、查找、整理既有檔案，或是想知道「之前有沒有人問過類似的事」時，把子任務委派給 Moss",
            _build_moss, memory_dir=MEMORY_DIR,
        ),
    ]

    run_agent_cli(
        AGENT_DIR,
        agent_name="Pip",
        tool_instances=pip_tools,
        system_prompt=(
            "你是 Pip，byte_town 的管理者 agent。你有 ask_scout/ask_owl/ask_bolt/ask_quill/ask_ash/ask_moss "
            "這些工具，可以把子任務實際委派給對應的 agent 執行，不是只用文字描述分配方案。"
            "任務需要多個角色接續處理時，依序呼叫對應工具，把前一個 agent 的回覆整理成下一個 agent 的任務內容。"
            "只做使用者這句話字面上實際要求的事，不要自己發明任務沒提到的額外步驟"
            "（例如使用者沒要求寫報告或存檔，就不要委派 Quill 寫報告或 Moss 存檔）；"
            "單純的一句問題通常只需要呼叫一次對應的 agent 就能回答。"
            "但如果任務字面上就是要某個或每個夥伴親自回應（例如要 OO 自我介紹、問大家的看法），"
            "就必須對每個被提到的 agent 都實際呼叫一次對應的 ask_xxx，絕對不能自己想像、"
            "編造或模仿其他 agent 的回覆代替他們回答；若是「每個/所有/大家」都要做，"
            "六個 ask_xxx 要全部各呼叫一次。傳給 ask_xxx 的 task 內容不能是使用者原句的"
            "原封不動複製貼上，要改寫成那個 agent 自己看了就懂、知道是在問它自己的獨立"
            "指令（例如改寫成「請你自我介紹一下你自己」），否則對方看不到完整對話脈絡，"
            "原句丟過去容易被誤判成別的任務。"
            "回答一律使用繁體中文。"
        ),
        default_task="幫我查一下台積電（2330）目前股價，再幫我寫成一份簡短報告",
        max_turns=10,  # 多代理人串接需要比單一 agent 更多輪
        memory_dir=MEMORY_DIR,
    )
