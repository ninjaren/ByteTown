"""從 ZuZu（qwen3_4b）移植過來、去除耦合後的共用工具庫。

每個模組對應原本 qwen3_4b/tools 的一個檔案，邏輯保持一致，
差異只在於：
- 不再寫死磁碟路徑（WORKSPACE、CHART_DIR…），改成建構時可傳入
- 不再用模組層級全域變數存狀態（browse_url 的速率限制），改成 instance 自己的狀態
- 不再直接依賴 qwen3_4b 的 config.py，Ollama 專用的工具（vision）改成建構時傳參數
"""
from .system_tools import CurrentTimeTool
from .calculator_tools import CalculatorTool
from .misc_tools import ClipboardTool, QRCodeTool, IPInfoTool
from .weather_tools import WeatherTool
from .stock_tools import StockPriceTool, MarketIndexTool, MultiStockTool
from .crypto_tools import CryptoPriceTool, MultiCryptoTool, ExchangeRateTool
from .chart_tools import StockChartTool
from .github_tools import GithubTrendingTool
from .pdf_tools import ReadPdfTool, ReadPdfPageTool, SplitPdfTool
from .file_tools import (
    ListFilesTool, ReadFileTool, WriteFileTool, AppendFileTool,
    DeleteFileTool, ReadCsvTool, MoveFileTool,
)
from .web_tools import SearchWebTool, BrowseUrlTool, FetchRssTool, ExtractLinksTool
from .vision_tools import AnalyzeImageTool
from .workspace import WorkspaceGuard
from .delegate_tool import DelegateToAgentTool, make_delegate_tool
from .memory_tools import RecallMemoryTool, ListRecentSessionsTool

__all__ = [
    "WorkspaceGuard",
    "CurrentTimeTool", "CalculatorTool",
    "ClipboardTool", "QRCodeTool", "IPInfoTool",
    "WeatherTool",
    "StockPriceTool", "MarketIndexTool", "MultiStockTool",
    "CryptoPriceTool", "MultiCryptoTool", "ExchangeRateTool",
    "StockChartTool", "GithubTrendingTool",
    "ReadPdfTool", "ReadPdfPageTool", "SplitPdfTool",
    "ListFilesTool", "ReadFileTool", "WriteFileTool", "AppendFileTool",
    "DeleteFileTool", "ReadCsvTool", "MoveFileTool",
    "SearchWebTool", "BrowseUrlTool", "FetchRssTool", "ExtractLinksTool",
    "AnalyzeImageTool",
    "DelegateToAgentTool", "make_delegate_tool",
    "RecallMemoryTool", "ListRecentSessionsTool",
]
