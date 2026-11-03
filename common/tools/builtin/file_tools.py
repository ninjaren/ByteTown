"""移植自 qwen3_4b/tools/file_ops.py。

去耦合：原本的 WORKSPACE 常數 + 模組層級 _safe_path() 改成注入一個
WorkspaceGuard 實例（見 workspace.py），每個 agent 可以各自限制範圍。
"""
import csv
import shutil
from typing import Union
from pathlib import Path

from ..base import Tool, ToolResult
from .workspace import WorkspaceGuard


class _WorkspaceTool(Tool):
    """共用建構子：所有檔案工具都需要一個 WorkspaceGuard 來限制存取範圍。"""

    def __init__(self, guard: Union[WorkspaceGuard, str, Path]):
        self._guard = guard if isinstance(guard, WorkspaceGuard) else WorkspaceGuard(guard)


class ListFilesTool(_WorkspaceTool):
    # 列出資料夾內容（先列子目錄、再列檔案，各自按名稱排序），不傳 path 則列出 workspace 根目錄
    name = "list_files"
    description = "列出指定資料夾內的檔案與子目錄"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "要列出的資料夾路徑，留空則列根目錄"}},
    }

    def run(self, path: str = "", **kwargs) -> ToolResult:
        try:
            p = self._guard.safe_path(path) if path else self._guard.root
            if not p.is_dir():
                return ToolResult(output=None, error=f"不是資料夾：{p}")
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            lines = [f"{'[目錄]' if i.is_dir() else '[檔案]'} {i.name}" for i in items]
            return ToolResult(output=f"{p}\n" + "\n".join(lines) if lines else "（空資料夾）")
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))
        except Exception as e:
            return ToolResult(output=None, error=f"列出失敗：{e}")


class ReadFileTool(_WorkspaceTool):
    # 讀取文字檔案的全部內容，固定以 UTF-8 編碼讀取
    name = "read_file"
    description = "讀取指定路徑的文字檔案內容"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "檔案的完整路徑"}},
        "required": ["path"],
    }

    def run(self, path: str, **kwargs) -> ToolResult:
        try:
            return ToolResult(output=self._guard.safe_path(path).read_text(encoding="utf-8"))
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))
        except Exception as e:
            return ToolResult(output=None, error=f"讀取失敗：{e}")


class WriteFileTool(_WorkspaceTool):
    # 建立新檔案或完整覆寫現有內容，父資料夾不存在時自動建立
    name = "write_file"
    description = "建立或覆寫指定路徑的文字檔案"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "檔案的完整路徑"},
            "content": {"type": "string", "description": "要寫入的文字內容"},
        },
        "required": ["path", "content"],
    }

    def run(self, path: str, content: str, **kwargs) -> ToolResult:
        try:
            p = self._guard.safe_path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult(output=f"已寫入：{p}")
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))
        except Exception as e:
            return ToolResult(output=None, error=f"寫入失敗：{e}")


class AppendFileTool(_WorkspaceTool):
    # 在現有檔案末尾附加內容，不覆蓋原有資料；檔案不存在時自動建立（行為同 write_file）
    name = "append_file"
    description = "在現有檔案末尾附加文字，檔案不存在則自動建立"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "檔案的完整路徑"},
            "content": {"type": "string", "description": "要附加的文字內容"},
        },
        "required": ["path", "content"],
    }

    def run(self, path: str, content: str, **kwargs) -> ToolResult:
        try:
            p = self._guard.safe_path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(output=f"已附加至：{p}")
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))
        except Exception as e:
            return ToolResult(output=None, error=f"附加失敗：{e}")


class DeleteFileTool(_WorkspaceTool):
    # 永久刪除指定檔案（不可復原），僅允許刪除檔案，不能刪除整個目錄
    name = "delete_file"
    description = "永久刪除指定檔案（不可復原），只能刪除單一檔案，不能刪除目錄"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "要刪除的檔案完整路徑"}},
        "required": ["path"],
    }

    def run(self, path: str, **kwargs) -> ToolResult:
        try:
            p = self._guard.safe_path(path)
            if not p.exists():
                return ToolResult(output=None, error=f"檔案不存在：{p}")
            if p.is_dir():
                return ToolResult(output=None, error=f"這是目錄，不能用 delete_file 刪除：{p}")
            p.unlink()
            return ToolResult(output=f"已刪除：{p}")
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))
        except Exception as e:
            return ToolResult(output=None, error=f"刪除失敗：{e}")


class ReadCsvTool(_WorkspaceTool):
    # 讀取 CSV 並回傳結構化摘要；自動依序嘗試常見編碼（UTF-8 → Big5 → CP950，台灣券商常見）
    name = "read_csv"
    description = "讀取 CSV 檔案並回傳結構化摘要（欄位名稱、資料筆數、前 N 行預覽），自動偵測分隔符與編碼"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "CSV 檔案的完整路徑"},
            "max_rows": {"type": "integer", "description": "最多顯示幾行資料，預設 50"},
        },
        "required": ["path"],
    }

    def run(self, path: str, max_rows: int = 50, **kwargs) -> ToolResult:
        try:
            p = self._guard.safe_path(path)
            if not p.exists():
                return ToolResult(output=None, error=f"檔案不存在：{p}")
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))

        content = None
        for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
            try:
                content = p.read_text(encoding=enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        if content is None:
            return ToolResult(output=None, error=f"無法解碼 CSV 檔案（嘗試過 utf-8、big5、cp950）：{p}")

        try:
            # 自動偵測分隔符（逗號 vs 分號 vs Tab）
            dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
            reader = csv.DictReader(content.splitlines(), dialect=dialect)
        except csv.Error:
            reader = csv.DictReader(content.splitlines())

        rows = list(reader)
        if not rows:
            return ToolResult(output=f"CSV 檔案是空的：{p}")

        headers = list(rows[0].keys())
        preview = rows[:max_rows]
        # 計算每欄顯示寬度用於對齊，單欄最大寬度限制 30 避免過長
        col_w = {h: min(max(len(h), max(len(str(r.get(h, ""))) for r in preview)), 30) for h in headers}

        def fmt_row(row: dict) -> str:
            return "  ".join(str(row.get(h, ""))[:col_w[h]].ljust(col_w[h]) for h in headers)

        lines = [
            f"【{p.name}】共 {len(rows)} 筆，{len(headers)} 個欄位",
            f"欄位：{', '.join(headers)}",
            "",
            "  ".join(h.ljust(col_w[h]) for h in headers),
            "  ".join("-" * col_w[h] for h in headers),
            *[fmt_row(r) for r in preview],
        ]
        if len(rows) > max_rows:
            lines.append(f"...（僅顯示前 {max_rows} 筆，剩餘 {len(rows) - max_rows} 筆）")
        return ToolResult(output="\n".join(lines))


class MoveFileTool(_WorkspaceTool):
    # 移動／重新命名檔案或目錄；來源與目標都必須在 WorkspaceGuard 的允許範圍內
    name = "move_file"
    description = "移動檔案或目錄到新路徑，也可用來重新命名。來源與目標都必須在允許範圍內"
    parameters = {
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "來源路徑（檔案或目錄）"},
            "dst": {"type": "string", "description": "目標路徑"},
        },
        "required": ["src", "dst"],
    }

    def run(self, src: str, dst: str, **kwargs) -> ToolResult:
        try:
            s, d = self._guard.safe_path(src), self._guard.safe_path(dst)
            if not s.exists():
                return ToolResult(output=None, error=f"來源不存在：{s}")
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(d))
            return ToolResult(output=f"已移動：{s}  →  {d}")
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))
        except Exception as e:
            return ToolResult(output=None, error=f"移動失敗：{e}")
