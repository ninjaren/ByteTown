import json
from typing import Optional

from ..base import LLMProvider, LLMResponse, ToolCall


def _to_ollama_tools(tools: list[dict]) -> list[dict]:
    # Ollama 的 tool-calling 格式跟 OpenAI 一致：{"type":"function","function":{...}}
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


class OllamaProvider(LLMProvider):
    """本地模型（透過 Ollama）的 adapter，不需要雲端 API key。"""

    def __init__(self, model: str = "llama3", host: str = "http://localhost:11434", **kwargs):
        super().__init__(model, **kwargs)
        self._host = host.rstrip("/")

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
        import requests  # 延遲匯入

        kwargs = {**self.extra, **kwargs}  # config.yaml 的 params 是建構時帶入的，這裡併回呼叫參數
        full_messages = ([{"role": "system", "content": system}] if system else []) + messages
        timeout = kwargs.pop("timeout", 120)
        if tools:
            kwargs["tools"] = _to_ollama_tools(tools)
        # qwen3 等思考模型預設會把推理過程跟最終答案分開放（content 常常是空的，
        # 答案藏在 thinking 欄位），agentic loop 需要穩定從 content 拿到最終文字，
        # 所以預設關掉 think；config.yaml 的 params 明確指定 think 時仍可覆寫
        kwargs.setdefault("think", False)

        resp = requests.post(
            f"{self._host}/api/chat",
            json={"model": self.model, "messages": full_messages, "stream": False, **kwargs},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        message = data["message"]

        # Ollama 的 tool_calls 通常沒有 id，也沒有強制 arguments 要是字串還是 dict，
        # 兩種情況都處理，並用索引補一個 id 方便之後對應
        tool_calls = []
        for i, tc in enumerate(message.get("tool_calls") or []):
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args)
            tool_calls.append(ToolCall(id=tc.get("id", f"call_{i}"), name=fn.get("name"), arguments=args))

        return LLMResponse(
            text=message.get("content", ""),
            raw=data,
            tool_calls=tool_calls,
            assistant_message=dict(message),
        )

    def format_tool_results(self, tool_calls: list[ToolCall], results: list[str]) -> list[dict]:
        # Ollama 不需要 tool_call_id 對應，依序各包一則 role=tool 訊息即可
        return [{"role": "tool", "content": r} for r in results]
