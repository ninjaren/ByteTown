"""移植自 qwen3_4b/tools/chart.py。

去耦合：CHART_DIR 原本寫死成 F:\\python_project\\ai_agent\\data\\charts，
改成建構時傳入 output_dir。
"""
from datetime import datetime
from pathlib import Path
from typing import Union

from ..base import Tool, ToolResult

YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
VALID_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y"}


def _tw_symbol(symbol: str) -> str:
    # 純數字台股代碼自動補 .TW（若已有後綴則不改）
    s = symbol.strip().upper()
    return s + ".TW" if s.replace(".", "").isdigit() and "." not in s else s


def _moving_avg(data, n: int):
    # 計算 N 日均線，前 n-1 天沒有足夠資料所以填 None
    result = [None] * (n - 1)
    for i in range(n - 1, len(data)):
        window = [v for v in data[i - n + 1: i + 1] if v is not None]
        result.append(sum(window) / len(window) if len(window) == n else None)
    return result


class StockChartTool(Tool):
    # 繪製股票價格走勢圖（折線 + MA5 + MA20 + 成交量），存為 PNG 並回傳路徑
    name = "plot_stock_chart"
    description = (
        "繪製股票價格走勢圖並存為 PNG 圖片，包含收盤價折線、MA5、MA20 均線與成交量柱狀圖。"
        "台股輸入純數字代碼（如 2330）會自動加 .TW；美股輸入英文代碼（如 AAPL）。"
        "period 可選：1mo / 3mo / 6mo / 1y / 2y / 5y，預設 3mo"
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "股票代碼，例如：2330、AAPL"},
            "period": {"type": "string", "description": "查詢區間，預設 3mo"},
        },
        "required": ["symbol"],
    }

    def __init__(self, output_dir: Union[str, Path]):
        self._output_dir = Path(output_dir)

    def run(self, symbol: str, period: str = "3mo", **kwargs) -> ToolResult:
        import requests
        import matplotlib
        matplotlib.use("Agg")  # Agg 後端不需要顯示視窗，適合伺服器環境
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import matplotlib.ticker as mticker

        sym = _tw_symbol(symbol)
        period = period if period in VALID_PERIODS else "3mo"  # 傳入非法值時 fallback 至 3mo

        # ── 取得歷史資料 ──────────────────────────────
        try:
            resp = requests.get(YF_URL.format(symbol=sym), headers=YF_HEADERS, params={"interval": "1d", "range": period}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return ToolResult(output=None, error=f"圖表資料取得失敗（{sym}）：{e}")

        try:
            result = data["chart"]["result"]
            if not result:
                return ToolResult(output=None, error=f"找不到股票代碼：{sym}")

            meta = result[0]["meta"]
            timestamps = result[0].get("timestamp", [])
            quote = result[0]["indicators"]["quote"][0]
            closes, opens, volumes = quote.get("close", []), quote.get("open", []), quote.get("volume", [])

            if not timestamps or not closes:
                return ToolResult(output=None, error=f"無法取得 {sym} 的歷史資料（可能是非交易日或代碼錯誤）")

            # 過濾 None（可能有節假日空洞）
            dates = [datetime.fromtimestamp(ts) for ts in timestamps]
            valid = [(d, c, o, v) for d, c, o, v in zip(dates, closes, opens, volumes) if c is not None]
            if not valid:
                return ToolResult(output=None, error=f"{sym} 的歷史資料全為空（非交易時段）")

            dates, closes, opens, volumes = zip(*valid)
            dates, closes, opens = list(dates), list(closes), list(opens)
            volumes = [v or 0 for v in volumes]
            name = meta.get("longName") or meta.get("shortName") or sym
            currency = meta.get("currency", "")
        except (KeyError, IndexError, TypeError) as e:
            return ToolResult(output=None, error=f"歷史資料解析失敗（{sym}）：{e}")

        # ── 計算均線 ──────────────────────────────────
        ma5, ma20 = _moving_avg(closes, 5), _moving_avg(closes, 20)

        # ── 繪圖：上方價格子圖佔 3/4，下方成交量子圖佔 1/4，共享 X 軸 ──
        # 配色採用 GitHub dark 主題：#0d1117 最暗背景、#161b22 次暗背景、#8b949e 灰字、#30363d 邊框
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
        fig.patch.set_facecolor("#0d1117")
        for ax in (ax1, ax2):
            ax.set_facecolor("#161b22")
            ax.tick_params(colors="#8b949e", labelsize=9)
            for spine in ax.spines.values():
                spine.set_edgecolor("#30363d")

        # 收盤價折線（zorder=3 讓它壓在均線上方）+ MA5（橘）/ MA20（紫）
        ax1.plot(dates, closes, color="#58a6ff", linewidth=1.2, label="收盤價", zorder=3)
        ma5_dates = [d for d, v in zip(dates, ma5) if v is not None]
        ma5_vals = [v for v in ma5 if v is not None]
        ma20_dates = [d for d, v in zip(dates, ma20) if v is not None]
        ma20_vals = [v for v in ma20 if v is not None]
        if ma5_dates:
            ax1.plot(ma5_dates, ma5_vals, color="#f0883e", linewidth=0.9, label="MA5", alpha=0.8)
        if ma20_dates:
            ax1.plot(ma20_dates, ma20_vals, color="#bc8cff", linewidth=0.9, label="MA20", alpha=0.8)

        ax1.set_ylabel(f"價格 ({currency})", color="#8b949e", fontsize=9)
        ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
        ax1.legend(loc="upper left", fontsize=8, facecolor="#161b22", edgecolor="#30363d", labelcolor="#c9d1d9")
        ax1.grid(color="#21262d", linewidth=0.5, linestyle="--", alpha=0.7)
        ax1.set_title(f"{name} ({sym})  ·  {period} 走勢", color="#e6edf3", fontsize=11, pad=8, fontweight="bold")

        # 成交量柱狀圖：收盤 >= 開盤 → 漲（綠），反之 → 跌（紅）
        colors = ["#3fb950" if c >= o else "#f85149" for c, o in zip(closes, opens)]
        ax2.bar(dates, volumes, color=colors, width=0.8, alpha=0.85)
        max_vol = max(volumes) if volumes else 1  # 自動縮放單位（百萬/千）
        if max_vol >= 1_000_000:
            ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v / 1e6:.1f}M"))
        elif max_vol >= 1_000:
            ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v / 1e3:.0f}K"))
        ax2.set_ylabel("成交量", color="#8b949e", fontsize=9)
        ax2.grid(color="#21262d", linewidth=0.5, linestyle="--", alpha=0.7, axis="y")

        # X 軸日期格式依資料長度調整，避免刻度太密
        if len(dates) <= 35:
            ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
            ax2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
        elif len(dates) <= 130:
            ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
            ax2.xaxis.set_major_locator(mdates.MonthLocator())
        else:
            ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y/%m"))
            ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))

        plt.xticks(rotation=30, ha="right", color="#8b949e", fontsize=8)
        plt.tight_layout(pad=1.5)

        # ── 存檔 ──────────────────────────────────────
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._output_dir / f"{sym.replace('.', '_')}_{period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        return ToolResult(output=str(out_path))
