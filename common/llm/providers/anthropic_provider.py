import os
from typing import Optional

from ..base import LLMProvider, LLMResponse, ToolCall


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    # 把我們統一的 Tool.to_schema() 格式翻譯成 Anthropic 要的 input_schema 格式
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t.get("parameters") or {"type": "object", "properties": {}}}
        for t in tools
    ]


class AnthropicProvider(LLMProvider):
    """Claude 系列模型的 adapter。"""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        import anthropic  # 延遲匯入：沒裝 anthropic 套件但用其他 provider 時不會報錯

        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def generate(self, prompt: str, *, system: Optional[str] = None, **kwargs) -> LLMResponse:
        return self.chat([{"role": "user", "content": prompt}], system=system, **kwargs)

    def chat(
        self,
        messages: list[dict],
        *,
        system: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        **kwargs,
    ) -> LLMResponse:
        kwargs = {**self.extra, **kwargs}  # config.yaml 的 params 是建構時帶入的，這裡併回呼叫參數
        max_tokens = kwargs.pop("max_tokens", 1024)
        if tools:
            kwargs["tools"] = _to_anthropic_tools(tools)

        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system or "",
            messages=messages,
            **kwargs,
        )

        # content 可能包含多種 block（text、tool_use 等），分別取出文字與工具呼叫
        text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
        tool_calls = [
            ToolCall(id=block.id, name=block.name, arguments=block.input)
            for block in resp.content if getattr(block, "type", None) == "tool_use"
        ]
        usage = resp.usage.model_dump() if getattr(resp, "usage", None) else None
        # 原樣保留這一輪的 content blocks，下一輪才能讓模型看到自己剛才呼叫了什麼工具
        assistant_message = {"role": "assistant", "content": [block.model_dump() for block in resp.content]}

        return LLMResponse(text=text, raw=resp, usage=usage, tool_calls=tool_calls, assistant_message=assistant_message)

    def format_tool_results(self, tool_calls: list[ToolCall], results: list[str]) -> list[dict]:
        # Anthropic 規定：同一輪的所有 tool_result 要包在同一則 role=user 訊息裡
        content = [{"type": "tool_result", "tool_use_id": tc.id, "content": r} for tc, r in zip(tool_calls, results)]
        return [{"role": "user", "content": content}]
