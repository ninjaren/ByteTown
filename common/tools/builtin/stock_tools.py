"""移植自 qwen3_4b/tools/stock.py，純功能無狀態，原樣搬入。

台股走台灣證交所官方 OpenAPI，美股走 Yahoo Finance，皆不需要 API Key。
"""
from ..base import Tool, ToolResult

# 台灣證交所 OpenAPI：全部上市股票的日成交資料／本益比資料／大盤指數
TWSE_DAY_ALL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_PE_ALL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
TWSE_INDEX = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
# Yahoo Finance 非官方 API，用來查美股或其他交易所
YF_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _roc_to_ad(roc_str: str) -> str:
    # TWSE 回應的日期是民國年，例如 "1151014" = 民國115年10月14日 = 2026-10-14
    try:
        return f"{int(roc_str[:3]) + 1911}-{roc_str[3:5]}-{roc_str[5:7]}"
    except Exception:
        return roc_str


def _is_tw_stock(symbol: str) -> bool:
    # 純數字視為台灣股票代碼（上市 4 碼、上櫃 4-5 碼）
    return symbol.replace(".", "").isdigit()


def _fetch_twse_all():
    # 一次性下載全部上市股票的日成交資料與本益比資料，回傳以代碼為 key 的查詢字典
    import requests

    try:
        r_day = requests.get(TWSE_DAY_ALL, timeout=15)
        r_day.raise_for_status()
        day_map = {row["Code"]: row for row in r_day.json()}
    except Exception:
        day_map = {}
    try:
        r_pe = requests.get(TWSE_PE_ALL, timeout=15)
        r_pe.raise_for_status()
        pe_map = {row["Code"]: row for row in r_pe.json()}
    except Exception:
        pe_map = {}
    return day_map, pe_map


def _get_tw_stock(code: str) -> str:
    # 查詢台灣上市股票（走 TWSE 官方 OpenAPI，中文名稱、日收盤資料）
    day_map, pe_map = _fetch_twse_all()
    row = day_map.get(code)
    if not row:
        return (f"找不到上市股票代碼：{code}\n"
                f"（上市股票才支援官方 API，上櫃股票請加 .TWO 後用 Yahoo Finance 查詢，如 6547.TWO）")

    name, date = row["Name"], _roc_to_ad(row["Date"])
    close, open_p, high, low = float(row["ClosingPrice"]), float(row["OpeningPrice"]), float(row["HighestPrice"]), float(row["LowestPrice"])
    vol_raw = row.get("TradeVolume", "").strip()
    vol = int(vol_raw) // 1000 if vol_raw.isdigit() else 0  # 單位：股 → 張（1張=1000股）
    change_str = row["Change"].strip()
    change = float(change_str) if change_str else 0.0  # Change 欄位帶正負號（漲為正、跌為負、平盤為 0）
    arrow = "▲" if change > 0 else ("▼" if change < 0 else "－")

    lines = [
        f"【{name}】{code}  （台灣證交所官方資料）",
        f"日期：{date}",
        f"收盤價：{close:.2f} TWD",
        f"漲跌：{arrow} {abs(change):.2f}",
        f"今日：開 {open_p:.2f} ／高 {high:.2f} ／低 {low:.2f}",
        f"成交量：{vol:,} 張",
    ]
    # 附加本益比、殖利率、股價淨值比（若有）
    pe = pe_map.get(code)
    if pe:
        extras = []
        if pe.get("PEratio"): extras.append(f"本益比 {pe['PEratio']}")
        if pe.get("DividendYield"): extras.append(f"殖利率 {pe['DividendYield']}%")
        if pe.get("PBratio"): extras.append(f"股價淨值比 {pe['PBratio']}")
        if extras:
            lines.append("估值：" + "　".join(extras))
    lines.append("※ 資料為當日收盤後更新，非即時報價")
    return "\n".join(lines)


def _get_yf_stock(symbol: str) -> str:
    # 查詢美股或其他交易所（走 Yahoo Finance，可傳入如 "6547.TWO" 查上櫃股）
    import requests

    try:
        resp = requests.get(YF_URL.format(symbol=symbol), headers=YF_HEADERS, params={"interval": "1d", "range": "2d"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"股價查詢失敗（{symbol}）：{e}"

    try:
        result = data["chart"]["result"]
        if not result:
            return f"找不到股票代碼：{symbol}"
        meta = result[0]["meta"]
        price, prev = meta.get("regularMarketPrice"), meta.get("previousClose") or meta.get("chartPreviousClose")
        day_high, day_low, volume = meta.get("regularMarketDayHigh"), meta.get("regularMarketDayLow"), meta.get("regularMarketVolume")
        currency = meta.get("currency", "")
        name = meta.get("longName") or meta.get("shortName") or symbol
        exchange = meta.get("exchangeName", "")

        if price is None or prev is None:
            return f"查到了 {symbol} 但價格資料不完整（可能非交易時間）"

        change = price - prev
        change_pct = (change / prev) * 100
        arrow = "▲" if change >= 0 else "▼"
        vol_str = "N/A"
        if volume:
            vol_str = f"{volume / 1_000_000:.2f}M" if volume >= 1_000_000 else f"{volume:,}"

        lines = [
            f"【{name}】{symbol}  ({exchange})",
            f"現價：{price:,.2f} {currency}",
            f"漲跌：{arrow} {abs(change):,.2f}  ({change_pct:+.2f}%)",
            f"今日：最高 {day_high:,.2f} ／最低 {day_low:,.2f}" if day_high and day_low else "",
            f"昨收：{prev:,.2f}",
            f"成交量：{vol_str}",
        ]
        return "\n".join(l for l in lines if l)
    except (KeyError, IndexError, TypeError) as e:
        return f"股價資料解析失敗（{symbol}）：{e}"


def _get_stock_price(symbol: str) -> str:
    # 依代碼格式分派：純數字 → 台股官方 API；其他 → Yahoo Finance
    s = symbol.strip().upper()
    return _get_tw_stock(s) if _is_tw_stock(s) else _get_yf_stock(s)


def _get_market_index() -> str:
    # 查詢台灣大盤指數，只取最重要的幾個指數
    import requests

    try:
        resp = requests.get(TWSE_INDEX, timeout=10)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        return f"大盤指數查詢失敗：{e}"

    target = {"發行量加權股價指數", "未含金融保險股指數", "未含電子股指數", "臺灣50指數"}
    lines, date_str = [], ""
    for row in rows:
        name = row.get("指數", "")
        if name not in target:
            continue
        if not date_str and row.get("日期"):
            date_str = _roc_to_ad(row["日期"])
        arrow = "▲" if row.get("漲跌") == "+" else ("▼" if row.get("漲跌") == "-" else "－")
        lines.append(f"{name}：{row.get('收盤指數', '')}  {arrow} {row.get('漲跌點數', '')}（{row.get('漲跌百分比', '')}%）")

    if not lines:
        return "無法取得大盤指數資料"
    return f"【台灣大盤指數】{date_str}\n" + "\n".join(lines) + "\n※ 資料為當日收盤後更新"


def _get_multiple_stocks(symbols: str) -> str:
    # 一次查詢多支股票，逗號分隔，例如 "2330,2454,AAPL"；台股批次只下載一次完整資料再過濾，避免重複呼叫
    tickers = [s.strip() for s in symbols.split(",") if s.strip()]
    if not tickers:
        return "請提供至少一個股票代碼"
    if len(tickers) > 10:
        return "單次最多查詢 10 支股票"

    tw_codes = [t for t in tickers if _is_tw_stock(t)]
    us_codes = [t for t in tickers if not _is_tw_stock(t)]
    results = []

    if tw_codes:
        day_map, _ = _fetch_twse_all()
        for code in tw_codes:
            row = day_map.get(code)
            if not row:
                results.append(f"【{code}】找不到上市股票資料")
                continue
            change_str = row.get("Change", "").strip()
            change = float(change_str) if change_str else 0.0
            arrow = "▲" if change > 0 else ("▼" if change < 0 else "－")
            results.append(f"【{row['Name']}】{code}  {float(row['ClosingPrice']):.2f} TWD  {arrow} {abs(change):.2f}  ({_roc_to_ad(row['Date'])})")

    for sym in us_codes:
        results.append(_get_yf_stock(sym))

    return "\n\n─────\n\n".join(results)


class StockPriceTool(Tool):
    # 查詢單一股票的報價與基本資訊
    name = "get_stock_price"
    description = "查詢單一股票的報價與基本資訊。台股輸入純數字代碼（如 2330），上櫃請加 .TWO，美股輸入英文代碼（如 AAPL）"
    parameters = {
        "type": "object",
        "properties": {"symbol": {"type": "string", "description": "股票代碼，例如：2330、AAPL、6547.TWO"}},
        "required": ["symbol"],
    }

    def run(self, symbol: str, **kwargs) -> ToolResult:
        return ToolResult(output=_get_stock_price(symbol))


class MarketIndexTool(Tool):
    # 查詢台灣大盤指數
    name = "get_market_index"
    description = "查詢台灣大盤指數，包含發行量加權股價指數、未含金融股指數、未含電子股指數等"
    parameters = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        return ToolResult(output=_get_market_index())


class MultiStockTool(Tool):
    # 一次查詢多支股票
    name = "get_multiple_stocks"
    description = "一次查詢多支股票的報價摘要，代碼以逗號分隔，最多 10 支。台股與美股可混查"
    parameters = {
        "type": "object",
        "properties": {"symbols": {"type": "string", "description": "逗號分隔，例如：2330,2454,AAPL"}},
        "required": ["symbols"],
    }

    def run(self, symbols: str, **kwargs) -> ToolResult:
        return ToolResult(output=_get_multiple_stocks(symbols))
