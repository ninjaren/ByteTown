"""移植自 qwen3_4b/tools/vision.py。

去耦合：
- 原本直接 import qwen3_4b 的 config.py（OLLAMA_URL / VISION_MODEL），
  改成建構時傳入 host / vision_model，不依賴任何特定專案的設定檔
- 原本直接 import tools.file_ops._safe_path，改成注入 WorkspaceGuard

注意：這個工具本質上是「直接打 Ollama 的 vision 模型」，沒有經過
common/llm 的 LLMProvider 抽象層，所以不是真正 LLM-agnostic —— 如果
之後某個 agent 換成 Anthropic/OpenAI，這個工具仍然只會呼叫本機 Ollama
的 vision 模型。先保留這個限制，等要支援多家 vision API 時再抽象。
"""
from typing import Union
from pathlib import Path

from ..base import Tool, ToolResult
from .workspace import WorkspaceGuard

SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


class AnalyzeImageTool(Tool):
    # 讀取本機圖片並透過視覺模型分析，回答關於圖片的問題
    name = "analyze_image"
    description = "分析本機圖片內容，可描述畫面、辨識文字、回答關於圖片的問題（內部固定使用 Ollama 的視覺模型處理）"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "圖片的完整路徑"},
            "question": {"type": "string", "description": "想詢問圖片的問題，預設為「請詳細描述這張圖片的內容」"},
        },
        "required": ["path"],
    }

    def __init__(
        self,
        guard: Union[WorkspaceGuard, str, Path],
        vision_model: str = "llava:7b",
        host: str = "http://localhost:11434",
    ):
        self._guard = guard if isinstance(guard, WorkspaceGuard) else WorkspaceGuard(guard)
        self._vision_model = vision_model
        self._host = host.rstrip("/")

    def run(self, path: str, question: str = "請詳細描述這張圖片的內容", **kwargs) -> ToolResult:
        import base64
        import requests

        try:
            p = self._guard.safe_path(path)
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))

        if not p.exists():
            return ToolResult(output=None, error=f"檔案不存在：{p}")
        if p.suffix.lower() not in SUPPORTED_FORMATS:
            return ToolResult(output=None, error=f"不支援的圖片格式：{p.suffix}（支援：{', '.join(SUPPORTED_FORMATS)}）")

        try:
            # 將圖片二進位資料轉成 base64 字串，Ollama API 要求此格式
            image_b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        except Exception as e:
            return ToolResult(output=None, error=f"圖片讀取失敗：{e}")

        try:
            resp = requests.post(
                f"{self._host}/api/chat",
                json={
                    "model": self._vision_model,
                    "messages": [{"role": "user", "content": question, "images": [image_b64]}],
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
            return ToolResult(output=resp.json()["message"]["content"])
        except Exception as e:
            return ToolResult(output=None, error=f"圖片分析失敗（請確認 {self._vision_model} 已透過 ollama pull 下載）：{e}")
