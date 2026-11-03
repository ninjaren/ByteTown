"""移植自 qwen3_4b/tools/pdf_ops.py。

去耦合：原本直接 import tools.file_ops._safe_path（綁死 qwen3_4b 的 WORKSPACE），
改成跟 file_tools 一樣注入 WorkspaceGuard。
"""
from typing import Union
from pathlib import Path

from ..base import Tool, ToolResult
from .workspace import WorkspaceGuard


class _WorkspaceTool(Tool):
    # 共用建構子：所有 PDF 工具都需要一個 WorkspaceGuard 來限制存取範圍
    def __init__(self, guard: Union[WorkspaceGuard, str, Path]):
        self._guard = guard if isinstance(guard, WorkspaceGuard) else WorkspaceGuard(guard)


class ReadPdfTool(_WorkspaceTool):
    # 讀取 PDF 全文，每頁用分隔線隔開方便閱讀；超長 PDF 可能超過模型 context window，建議改用 read_pdf_page
    name = "read_pdf"
    description = "讀取 PDF 檔案的全部文字內容。超長文件建議改用 read_pdf_page 分批讀取"
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "PDF 檔案的完整路徑"}},
        "required": ["path"],
    }

    def run(self, path: str, **kwargs) -> ToolResult:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(self._guard.safe_path(path)))
            pages = []
            for i, page in enumerate(reader.pages):
                text = (page.extract_text() or "").strip()
                if text:
                    pages.append(f"── 第 {i + 1} 頁 ──\n{text}")
            if not pages:
                return ToolResult(output="PDF 無可提取的文字（可能是掃描圖片版，需要 OCR）")
            return ToolResult(output=f"共 {len(reader.pages)} 頁\n\n" + "\n\n".join(pages))
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))
        except Exception as e:
            return ToolResult(output=None, error=f"PDF 讀取失敗：{e}")


class ReadPdfPageTool(_WorkspaceTool):
    # 讀取指定頁數範圍的文字（頁碼從 1 開始，含頭含尾），適合分批處理長篇文件
    name = "read_pdf_page"
    description = "讀取 PDF 指定頁數範圍的文字，適合分批處理長篇電子書（頁碼從 1 開始）"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "PDF 檔案的完整路徑"},
            "start_page": {"type": "integer", "description": "起始頁碼（含，從 1 開始）"},
            "end_page": {"type": "integer", "description": "結束頁碼（含）"},
        },
        "required": ["path", "start_page", "end_page"],
    }

    def run(self, path: str, start_page: int, end_page: int, **kwargs) -> ToolResult:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(self._guard.safe_path(path)))
            total = len(reader.pages)
            start, end = max(1, start_page), min(end_page, total)
            if start > total:
                return ToolResult(output=None, error=f"超出範圍：此 PDF 共 {total} 頁")
            pages = []
            for i in range(start - 1, end):
                text = (reader.pages[i].extract_text() or "").strip()
                if text:
                    pages.append(f"── 第 {i + 1} 頁 ──\n{text}")
            body = "\n\n".join(pages) if pages else "此範圍無可提取文字"
            return ToolResult(output=f"第 {start}-{end} 頁（共 {total} 頁）\n\n{body}")
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))
        except Exception as e:
            return ToolResult(output=None, error=f"PDF 讀取失敗：{e}")


class SplitPdfTool(_WorkspaceTool):
    # 從來源 PDF 切出指定頁數範圍，另存為新的 PDF 檔案；輸出路徑同樣受 WorkspaceGuard 限制
    name = "split_pdf"
    description = "從 PDF 切出指定頁數範圍，儲存成新的 PDF 檔案"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "來源 PDF 的完整路徑"},
            "start_page": {"type": "integer", "description": "起始頁碼（含，從 1 開始）"},
            "end_page": {"type": "integer", "description": "結束頁碼（含）"},
            "output_path": {"type": "string", "description": "輸出 PDF 的完整路徑"},
        },
        "required": ["path", "start_page", "end_page", "output_path"],
    }

    def run(self, path: str, start_page: int, end_page: int, output_path: str, **kwargs) -> ToolResult:
        try:
            from pypdf import PdfReader, PdfWriter
            src, dst = self._guard.safe_path(path), self._guard.safe_path(output_path)
            reader = PdfReader(str(src))
            total = len(reader.pages)
            start, end = max(1, start_page), min(end_page, total)
            if start > total:
                return ToolResult(output=None, error=f"超出範圍：此 PDF 共 {total} 頁")
            writer = PdfWriter()
            for i in range(start - 1, end):
                writer.add_page(reader.pages[i])
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(dst, "wb") as f:
                writer.write(f)
            return ToolResult(output=f"已切出第 {start}-{end} 頁（共 {end - start + 1} 頁），存至：{dst}")
        except PermissionError as e:
            return ToolResult(output=None, error=str(e))
        except Exception as e:
            return ToolResult(output=None, error=f"PDF 切割失敗：{e}")
