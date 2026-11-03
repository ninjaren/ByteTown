"""移植自 qwen3_4b/tools/system.py，純功能無狀態，原樣搬入。"""
from datetime import datetime

from ..base import Tool, ToolResult


class CurrentTimeTool(Tool):
    # 模型的訓練資料有截止日期，任何需要「今天」的場景都應呼叫此工具，不可自行猜測
    name = "get_current_time"
    description = "取得目前的日期和時間"
    parameters = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        # 格式：YYYY-MM-DD HH:MM:SS
        return ToolResult(output=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
