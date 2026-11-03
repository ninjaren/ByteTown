"""共用的 agentic loop。

讓 LLM 自己決定要不要呼叫工具、呼叫哪個，呼叫完把結果餵回去讓它繼續推理，
直到它給出最終答案或達到輪數上限為止——這是 ZuZu（qwen3_4b/agent.py）原本就有、
但 byte_town 框架一直缺的那塊：之前的範例是程式自己先手動呼叫工具，
不是讓模型自主判斷。

這份迴圈完全不知道底層是哪家 LLM。三家 provider 在 tool-calling 上的格式差異
（Anthropic 的 tool_use content block、OpenAI/Ollama 的 tool_calls 列表），
全部由 LLMProvider.chat() 回傳的統一 ToolCall，以及 format_tool_results()
這兩個介面方法吸收掉，新增第四家 LLM 時完全不需要碰這個檔案。
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from .llm.base import LLMProvider
from .logging_utils import RunLogger
from .tools.registry import ToolRegistry


@dataclass
class AgentLoopResult:
    text: str  # 模型的最終回答
    turns_used: int  # 實際跑了幾輪（每輪可能包含零到多個工具呼叫）
    tool_log: list = field(default_factory=list)  # [(工具名, 參數, 結果字串), ...]，方便除錯與追蹤
    messages: list = field(default_factory=list)  # 完整對話紀錄，可接續下一次呼叫


def run_agentic_loop(
    llm: LLMProvider,
    tools: ToolRegistry,
    messages: list[dict],
    *,
    system: Optional[str] = None,
    max_turns: int = 6,
    on_tool_call: Optional[Callable[[str, dict], None]] = None,
    logger: Optional[RunLogger] = None,
) -> AgentLoopResult:
    """執行一次完整的 agentic loop。

    messages 會被直接修改（append 新的輪次），呼叫端若要保留原始列表請自行複製。
    on_tool_call 是可選的回呼，每次模型決定呼叫工具時會被呼叫一次，方便印出進度。
    logger 是可選的 RunLogger（見 common/logging_utils.py），每一輪、每次工具呼叫
    都會立刻寫入並 flush，讓呼叫端萬一在跑到一半時當掉，也查得到執行到哪裡。
    """
    schemas = tools.list_schemas() or None  # 沒有工具時傳 None，避免送出空的 tools 陣列
    tool_log: list = []
    response = None

    try:
        for turn in range(1, max_turns + 1):
            if logger:
                logger.turn_start(turn)

            response = llm.chat(messages, system=system, tools=schemas)

            # 把這一輪「助手說的話」原樣加回對話紀錄，模型才看得到自己剛才呼叫了什麼工具
            if response.assistant_message is not None:
                messages.append(response.assistant_message)

            if logger:
                logger.llm_response(response.text, response.tool_calls)

            if not response.tool_calls:
                # 沒有工具呼叫，代表模型已經給出最終答案
                if logger:
                    logger.final(response.text)
                return AgentLoopResult(text=response.text, turns_used=turn, tool_log=tool_log, messages=messages)

            # 依序執行這一輪模型要求的每個工具呼叫，收集結果準備餵回去
            results: list[str] = []
            for tc in response.tool_calls:
                if on_tool_call:
                    on_tool_call(tc.name, tc.arguments)

                if tc.name not in tools:
                    result_text = f"未知工具：{tc.name}"
                else:
                    try:
                        tool_result = tools.run(tc.name, **tc.arguments)
                        result_text = str(tool_result.output) if tool_result.ok else f"錯誤：{tool_result.error}"
                    except Exception as e:
                        result_text = f"工具執行失敗：{e}"

                if logger:
                    logger.tool_result(tc.name, tc.arguments, result_text)

                tool_log.append((tc.name, tc.arguments, result_text))
                results.append(result_text)

            # 若這一輪呼叫到任何標記為 terminal 的工具，直接拿它的原始結果當最終答案，
            # 不要再送回 LLM 讓它重新敘述——避免小模型為了「湊得更完整」而捏造內容
            if any(tc.name in tools and tools.get(tc.name).terminal for tc in response.tool_calls):
                messages.extend(llm.format_tool_results(response.tool_calls, results))
                final_text = "\n\n".join(results)
                if logger:
                    logger.final(final_text)
                return AgentLoopResult(text=final_text, turns_used=turn, tool_log=tool_log, messages=messages)

            # 把工具結果包裝成這家 LLM 要求的格式，加回對話紀錄後進入下一輪
            messages.extend(llm.format_tool_results(response.tool_calls, results))
    except Exception as e:
        # 先把錯誤寫進 log 再往外拋，呼叫端才查得到「卡在哪一步」，不是只看到一個例外
        if logger:
            logger.error(str(e))
        raise

    # 達到最大輪數仍未得到不帶工具呼叫的最終答案，強制結束避免無限迴圈
    final_text = response.text if response else ""
    if logger:
        logger.final(final_text + "（已達最大輪數，強制結束）")
    return AgentLoopResult(
        text=final_text,
        turns_used=max_turns,
        tool_log=tool_log,
        messages=messages,
    )
