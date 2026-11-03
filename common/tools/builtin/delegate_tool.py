"""把「呼叫另一個 agent 的完整 agentic loop」包裝成一個 Tool。

這是多 agent 串接的核心機制：Manager（或任何 agent）不需要用文字描述
「這個任務該交給誰」，而是把其他 agent 包裝成像 search_web、read_file
一樣的工具，自己的 agentic loop 自然就能決定什麼時候呼叫哪個 agent，
被委派的 agent 一樣會自己判斷要不要呼叫它自己的工具/skill，
整個過程跟呼叫一般工具沒有結構上的差異，只是「工具」換成了另一個 agent。
"""
from pathlib import Path
from typing import Callable, Optional, Union

from ..base import Tool, ToolResult
from ...logging_utils import RunLogger

# 附加原始資料時，單筆工具結果最多保留的字數，避免一次把整篇長文章塞進委派結果
_RAW_ENTRY_MAX_CHARS = 500


def _format_tool_log(tool_log: list) -> str:
    # 把這個 agent 內部實際呼叫工具得到的原始結果整理成一段文字，
    # 讓委派它的上層 agent 轉述時有東西可以直接複製數字，不用憑印象重建
    lines = []
    for name, args, text in tool_log:
        text = str(text)
        if len(text) > _RAW_ENTRY_MAX_CHARS:
            text = text[:_RAW_ENTRY_MAX_CHARS] + "…（已截斷）"
        lines.append(f"- {name}({args})\n  → {text}")
    return "\n".join(lines)


class DelegateToAgentTool(Tool):
    def __init__(
        self,
        agent_key: str,
        agent_label: str,
        description: str,
        build_agent: Callable,
        max_turns: int = 6,
        memory_dir: Optional[Union[str, Path]] = None,
    ):
        # build_agent 是延遲建立函式：() -> (llm, tools, skills, system_prompt)
        # 延遲到真正被呼叫才建立，避免 Manager 啟動時就要把所有子 agent 的 LLM/工具都建好
        self.name = f"ask_{agent_key}"
        self.description = description
        self.parameters = {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": f"要委派給{agent_label}的子任務說明，請具體描述要做什麼"},
            },
            "required": ["task"],
        }
        self._agent_key = agent_key
        self._agent_label = agent_label
        self._build_agent = build_agent
        self._max_turns = max_turns
        self._memory_dir = memory_dir

    def run(self, task: str, **kwargs) -> ToolResult:
        # 延遲匯入：common.agent 不依賴 common.tools.builtin，但反過來在模組載入時
        # 互相 import 仍有風險，把它放進 run() 裡面在真正執行時才匯入最安全
        from ...agent import run_agentic_loop

        llm, tools, skills, system_prompt = self._build_agent()

        # 跟每個 agent 自己的 run_agent.py 一樣：依任務內容的關鍵字配對該用哪個 skill；
        # 沒命中就不套 skill，直接用原始任務，不要硬套清單裡第一個 skill
        matched = skills.find_by_keyword(task)
        skill = matched[0] if matched else None
        prompt = skill.render(task=task) if skill else task

        # 被委派的子任務一樣要寫逐輪 log，不然多代理人串接時某個子 agent 卡住，
        # 從上層完全看不出是哪一步出的問題（跟 agent_runner.py 用同一套 RunLogger）
        log_dir = Path(self._memory_dir).parent / "logs" if self._memory_dir is not None else None
        logger = RunLogger(log_dir, self._agent_key.capitalize()) if log_dir is not None else None
        if logger:
            logger.task(self._agent_key.capitalize(), task, skill_name=skill.name if skill else None)

        try:
            result = run_agentic_loop(
                llm,
                tools,
                [{"role": "user", "content": prompt}],
                system=system_prompt,
                max_turns=self._max_turns,
                logger=logger,
            )
        finally:
            if logger:
                logger.close()

        # 被委派的這次任務，一樣要存進共用記憶，不然只有「直接跑 run_agent.py」
        # 才會留下紀錄，Pip 幫忙轉介的這些任務反而什麼都沒留下
        if self._memory_dir is not None:
            from ...memory import build_default_memory, record_turn

            session_store, vector_memory = build_default_memory(self._memory_dir)
            record_turn(self._agent_key.capitalize(), task, result, session_store, vector_memory)

        output = f"[{self._agent_label} 的回覆]\n{result.text}"
        if result.tool_log:
            # 盲委派最大的風險是「轉述時漏掉關鍵數字」，所以把原始工具結果一起附上，
            # 委派下一個任務時可以直接複製這裡的數字，不用靠自己憑印象重建
            output += (
                f"\n\n[{self._agent_label} 實際查到的原始資料，"
                f"委派下一個任務時請把需要的數字或內容直接複製過去，不要自己憑印象轉述]\n"
                f"{_format_tool_log(result.tool_log)}"
            )
        return ToolResult(output=output)


def make_delegate_tool(
    agent_key: str,
    agent_label: str,
    description: str,
    build_agent: Callable,
    max_turns: int = 6,
    memory_dir: Optional[Union[str, Path]] = None,
) -> DelegateToAgentTool:
    return DelegateToAgentTool(agent_key, agent_label, description, build_agent, max_turns, memory_dir)
