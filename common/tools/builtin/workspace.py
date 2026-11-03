"""檔案類工具共用的路徑安全檢查。

原本 qwen3_4b/tools/file_ops.py 把允許範圍寫死成 WORKSPACE = F:\\python_project\\ai_agent，
這裡改成建構時傳入 root，讓每個 agent 可以各自限制自己能動到哪個目錄
（例如 Moss 可以存取整個 byte_town/data，Bolt 只能動自己負責的程式碼目錄）。
"""
import os
from pathlib import Path
from typing import Union


class WorkspaceGuard:
    def __init__(self, root: Union[str, Path]):
        self.root = Path(root).resolve()

    def safe_path(self, path: str) -> Path:
        # 解析為絕對路徑並確認落在 root 範圍內，防止路徑穿越攻擊
        # 加 os.sep 避免誤判："byte_town" 是 "byte_townX" 的字串前綴，但後者不是合法子路徑
        p = Path(path).resolve()
        if p != self.root and not str(p).startswith(str(self.root) + os.sep):
            raise PermissionError(f"路徑超出允許範圍：{p}（只允許 {self.root}）")
        return p
