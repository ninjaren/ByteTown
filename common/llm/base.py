"""所有 LLM 供應商共用的介面。

上層的 agent / skill 程式碼只依賴這個介面，不直接依賴任何廠商的 SDK，
換模型只需要換 config.yaml 裡的 provider/model，不需要改程式碼。

tool-calling 的格式三家都不一樣（Anthropic 用 tool_use content block、
OpenAI/Ollama 用 tool_calls 列表），所以這裡定義一個統一的 ToolCall，
各 provider 自己負責把廠商格式「翻譯」成這個統一格式，
agentic loop（見 common/agent.py）完全不需要知道底層是哪家 LLM。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    # 統一格式的工具呼叫請求：id 用來在送回工具結果時對應回這次呼叫
    # （Ollama 原生不一定有 id，provider 會自己補一個）
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str
    raw: Any = None
    usage: Optional[dict] = field(default=None)
    # 這一輪模型要求呼叫的工具，空列表代表模型直接回答，不需要呼叫工具
    tool_calls: list[ToolCall] = field(default_factory=list)
    # 這一輪「助手說的話」的廠商原生格式，agentic loop 要原樣把它加回 messages
    # 才能讓模型在下一輪看到自己剛才呼叫了哪些工具
    assistant_message: Optional[dict] = None


class LLMProvider(ABC):
    def __init__(self, model: str, **kwargs):
        self.model = model
        self.extra = kwargs  # 建構時多傳的參數（例如 config.yaml 的 params），由各 provider 自行決定何時套用

    @abstractmethod
    def generate(self, prompt: str, *, system: Optional[str] = None, **kwargs) -> LLMResponse:
        """單輪文字生成，不支援工具呼叫。"""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        *,
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        **kwargs,
    ) -> LLMResponse:
        """多輪對話，messages 格式統一為 [{"role": "user"/"assistant"/"tool", "content": ...}, ...]。

        tools 是 Tool.to_schema() 的清單（{"name", "description", "parameters"}），
        provider 內部會翻譯成自己 API 要的格式；不需要工具呼叫時可以不傳。
        """

    @abstractmethod
    def format_tool_results(self, tool_calls: list[ToolCall], results: list[str]) -> list[dict]:
        """把這一輪所有工具的執行結果，包裝成這家 LLM API 要求的訊息格式，
        回傳的訊息直接 append 進 messages 列表即可（可能是一則或多則）。
        """
