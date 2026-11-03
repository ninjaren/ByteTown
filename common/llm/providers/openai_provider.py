import json
import os
from typing import Optional

from ..base import LLMProvider, LLMResponse, ToolCall


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    # 把我們統一的 Tool.to_schema() 格式翻譯成 OpenAI 的 function-calling 格式
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("parameters") or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


class OpenAIProvider(LLMProvider):
    """GPT 系列模型的 adapter。"""

    def __init__(self, model: str = "gpt-4o", api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        from openai import OpenAI  # 延遲匯入

        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

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
        full_messages = ([{"role": "system", "content": system}] if system else []) + messages
        if tools:
            kwargs["tools"] = _to_openai_tools(tools)

        resp = self._client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            **kwargs,
        )
        message = resp.choices[0].message
        usage = resp.usage.model_dump() if getattr(resp, "usage", None) else None

        # OpenAI 的 arguments 是 JSON 字串，要先解析成 dict 才能統一成 ToolCall
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments or "{}"))
            for tc in (message.tool_calls or [])
        ]
        # 原樣保留這一輪的 assistant 訊息（含 tool_calls），下一輪才能讓模型看到自己剛才呼叫了什麼工具
        assistant_message = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            assistant_message["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in message.tool_calls
            ]

        return LLMResponse(text=message.content or "", raw=resp, usage=usage, tool_calls=tool_calls, assistant_message=assistant_message)

    def format_tool_results(self, tool_calls: list[ToolCall], results: list[str]) -> list[dict]:
        # OpenAI 規定：每個工具結果各自用一則 role=tool 訊息，靠 tool_call_id 對應回原始呼叫
        return [{"role": "tool", "tool_call_id": tc.id, "content": r} for tc, r in zip(tool_calls, results)]
