"""所有工具共用的介面。

Tool 是「agent 可以呼叫的一個具體動作」（讀檔、搜尋、跑程式…）。
每個工具都要能產出給 LLM function-calling 用的 schema，
這樣不管底層換成哪家 LLM，工具的描述方式都一致。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolResult:
    output: Any
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Tool(ABC):
    name: str = ""
    description: str = ""
    # JSON schema 格式，描述這個工具接受的參數（給 LLM function-calling 用）
    parameters: dict = {}
    # 若為 True，這個工具的結果會直接當成 agentic loop 的最終答案，不會再送回 LLM
    # 讓它重新敘述。用在「資料查詢類」工具（例如查語意記憶）：小模型被要求轉述查詢結果時，
    # 有時會為了「湊得更完整」而捏造真實資料裡沒有的內容，寧可讓使用者看到工具的原始輸出，
    # 也不要冒著被模型「潤飾」出不存在的事實的風險。
    terminal: bool = False

    @abstractmethod
    def run(self, **kwargs) -> ToolResult:
        """實際執行工具邏輯。"""

    def to_schema(self) -> dict:
        # 給 LLM function-calling 用的描述，子類別可覆寫 parameters 的細節
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
