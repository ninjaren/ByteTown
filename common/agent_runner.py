"""共用的 agent CLI 執行器。

每個 agent 資料夾下的 run_agent.py 只需要提供「我是誰」「我有哪些工具」，
剩下的事（讀 config.yaml 選模型、依任務內容配對 skill、跑 agentic loop、
印出結果、存進共用記憶）都交給這裡處理，避免 7 個 run_agent.py 各自重複
同一段邏輯。
"""
import sys
from pathlib import Path
from typing import Optional, Union

from .agent import run_agentic_loop
from .llm import create_llm_from_config
from .logging_utils import RunLogger
from .memory import build_default_memory, record_turn
from .skills import SkillRegistry
from .tools import Tool, ToolRegistry


def run_agent_cli(
    agent_dir: Union[str, Path],
    agent_name: str,
    tool_instances: list[Tool],
    system_prompt: str,
    default_task: str,
    max_turns: int = 6,
    memory_dir: Optional[Union[str, Path]] = None,
) -> None:
    agent_dir = Path(agent_dir)

    # 1. 依 config.yaml 建立這個 agent 要用的 LLM（換 provider/model 只改 yaml）
    llm = create_llm_from_config(agent_dir / "config.yaml")

    # 2. 註冊這個 agent 的工具，交給模型自己決定要不要呼叫
    tools = ToolRegistry()
    for t in tool_instances:
        tools.register(t)

    # 3. 載入這個 agent 的所有 skill，依任務內容的關鍵字配對該用哪一個
    skills = SkillRegistry()
    skills.load_dir(agent_dir / "skills")

    task = sys.argv[1] if len(sys.argv) > 1 else default_task

    # 只有「任務文字真的命中某個 skill 的關鍵字」才套用該 skill 固定流程；
    # 完全沒命中就不套 skill、直接把原始任務丟給模型自由回答。
    # 之前這裡沒命中會硬套「清單裡第一個 skill」，導致任何不相關的任務
    # （例如要 agent 自我介紹）都被第一個 skill 的固定流程綁架
    # （例如 Owl 的第一個 skill 是「畫走勢圖」，結果被逼著去畫圖）。
    matched = skills.find_by_keyword(task)
    skill = matched[0] if matched else None

    if skill:
        print(f"[使用 skill] {skill.name}")
        prompt = skill.render(task=task)
    else:
        prompt = task

    def on_tool_call(name: str, args: dict) -> None:
        print(f"[呼叫工具] {name}  參數：{args}")

    # 4. 建立這次執行的 log（跟 memory_dir 共用同一個 data/ 目錄底下的 logs/，
    # 逐輪即時寫入，就算下面的 agentic loop 中途當掉也查得到卡在哪一步）
    log_dir = Path(memory_dir).parent / "logs" if memory_dir is not None else None
    logger = RunLogger(log_dir, agent_name) if log_dir is not None else None
    if logger:
        logger.task(agent_name, task, skill_name=skill.name if skill else None)

    try:
        # 5. 跑 agentic loop：模型自己判斷要不要呼叫工具、呼叫幾次
        result = run_agentic_loop(
            llm,
            tools,
            [{"role": "user", "content": prompt}],
            system=system_prompt,
            on_tool_call=on_tool_call,
            max_turns=max_turns,
            logger=logger,
        )
    finally:
        if logger:
            logger.close()

    print(f"\n（{agent_name} 共跑了 {result.turns_used} 輪，呼叫了 {len(result.tool_log)} 次工具）")
    print(f"\n回答：\n{result.text}")

    # 6. 把這次任務存進共用記憶（session 存檔 + 語意向量庫），供 Moss 之後查詢
    if memory_dir is not None:
        session_store, vector_memory = build_default_memory(memory_dir)
        session_id = record_turn(agent_name, task, result, session_store, vector_memory)
        if session_id:
            print(f"\n（已存入記憶：{session_id}）")
