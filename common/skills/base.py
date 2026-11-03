"""Skill = 一段「prompt 模板 + 使用情境 + 所需工具」的封裝。

跟寫死在程式裡的邏輯不同，skill 用 YAML 描述，
agent（或 Manager）可以在執行期依任務內容動態選擇要用哪個 skill。
"""
from dataclasses import dataclass, field


@dataclass
class Skill:
    name: str
    description: str
    trigger_keywords: list[str] = field(default_factory=list)
    prompt_template: str = ""
    required_tools: list[str] = field(default_factory=list)

    def render(self, **kwargs) -> str:
        # 把呼叫端準備好的資料（例如搜尋結果）套進 prompt_template 裡的 {佔位符}
        return self.prompt_template.format(**kwargs)
