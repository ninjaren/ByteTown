"""Owl（分析師）的執行入口。

執行： python 02_analyst_owl/run_agent.py "幫我查一下台積電股價，漲跌幅換算成百分比"
"""
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = AGENT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from common.agent_runner import run_agent_cli
from common.tools.builtin import (
    StockPriceTool, MarketIndexTool, MultiStockTool,
    CryptoPriceTool, MultiCryptoTool, ExchangeRateTool,
    CalculatorTool, StockChartTool,
)

DATA_DIR = ROOT_DIR / "data"

if __name__ == "__main__":
    run_agent_cli(
        AGENT_DIR,
        agent_name="Owl",
        tool_instances=[
            StockPriceTool(), MarketIndexTool(), MultiStockTool(),
            CryptoPriceTool(), MultiCryptoTool(), ExchangeRateTool(),
            CalculatorTool(), StockChartTool(output_dir=DATA_DIR / "charts"),
        ],
        system_prompt="你是 Owl，byte_town 的分析師 agent。回答一律使用繁體中文。",
        default_task="幫我查一下台積電（2330）目前股價",
        memory_dir=DATA_DIR / "memory",
    )
