"""逐輪即時寫入的執行記錄（log），跟 common/memory 的 session 存檔不一樣：

session 存檔（common/memory/session_store.py）是整個 agentic loop 跑完才一次性
寫入一份 JSON，給 Moss 之後做語意查詢用；這裡的 RunLogger 是「過程中每一步
就立刻寫入並 flush」，就算中途當掉、被中斷、或卡在某個工具呼叫不回應，
已經發生過的步驟也不會消失，方便回頭查是跑到哪一步出問題。

這裡記錄的是模型「外顯」的決策過程（每輪呼叫了什麼工具、工具回傳了什麼、
最後給出什麼答案），不是模型內部隱藏的推理——qwen3 等思考模型的 thinking
欄位已經在 OllamaProvider 刻意關閉（think=False，見 ollama_provider.py），
所以沒有東西可以記，這裡記的「過程」是以工具呼叫序列還原出的執行軌跡。
"""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Union


class RunLogger:
    def __init__(self, log_dir: Union[str, Path], agent_name: str):
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 檔名加短 uuid 避免多代理人串接時同一秒內有多個 log 檔互相覆蓋
        self._path = log_dir / f"{agent_name}_{timestamp}_{uuid.uuid4().hex[:6]}.log"
        self._fh = open(self._path, "a", encoding="utf-8")

    @property
    def path(self) -> Path:
        return self._path

    def _write(self, line: str) -> None:
        # 每寫一行就立刻 flush，確保「中途當掉前已經發生的事」一定留在檔案裡，
        # 不會卡在作業系統的寫入緩衝區裡遺失
        now = datetime.now().strftime("%H:%M:%S")
        self._fh.write(f"[{now}] {line}\n")
        self._fh.flush()

    def task(self, agent_name: str, task: str, skill_name: Optional[str] = None) -> None:
        skill_note = f"（套用 skill：{skill_name}）" if skill_name else ""
        self._write(f"=== {agent_name} 開始任務{skill_note}：{task} ===")

    def turn_start(self, turn: int) -> None:
        self._write(f"--- 第 {turn} 輪 ---")

    def llm_response(self, text: str, tool_calls: list) -> None:
        if tool_calls:
            names = ", ".join(tc.name for tc in tool_calls)
            self._write(f"模型決定呼叫工具：{names}")
        else:
            self._write(f"模型給出最終回答：{_truncate(text)}")

    def tool_result(self, name: str, args: dict, result_text: str) -> None:
        self._write(f"工具 {name}({args}) → {_truncate(result_text, 300)}")

    def final(self, text: str) -> None:
        self._write(f"=== 最終回答：{_truncate(text)} ===")

    def error(self, message: str) -> None:
        self._write(f"!!! 發生錯誤，執行中斷：{message}")

    def close(self) -> None:
        self._fh.close()


def _truncate(text: str, limit: int = 200) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "…（已截斷，完整內容見 session 存檔）"
