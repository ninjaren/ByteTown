"""工具的註冊與查詢。每個 agent 在啟動時把自己能用的工具註冊進來，
之後只要用名稱就能查到工具，也能一次拿到所有工具的 schema 丟給 LLM。
"""
from .base import Tool, ToolResult


class ToolRegistry:
    def __init__(self):
        # 用名稱當 key，一個 agent 一份自己的 registry，彼此不共用
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        # 同名工具不允許重複註冊，避免悄悄覆蓋掉另一個工具
        if tool.name in self._tools:
            raise ValueError(f"工具名稱重複: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def run(self, name: str, **kwargs) -> ToolResult:
        # 依名稱找到工具並直接執行，方便呼叫端不用自己先 get() 再呼叫
        return self.get(name).run(**kwargs)

    def list_schemas(self) -> list[dict]:
        # 彙整所有已註冊工具的 schema，丟給 LLM 做 function-calling
        return [t.to_schema() for t in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())
