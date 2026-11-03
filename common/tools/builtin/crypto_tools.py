"""移植自 qwen3_4b/tools/crypto.py，純功能無狀態，原樣搬入（CoinGecko / open.er-api.com，皆免 Key）。"""
from typing import Optional

from ..base import Tool, ToolResult

COINGECKO_PRICE = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_SEARCH = "https://api.coingecko.com/api/v3/search"
CG_HEADERS = {"User-Agent": "curl/7.68.0", "Accept": "application/json"}
ER_URL = "https://open.er-api.com/v6/latest/{base}"

_COIN_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin", "AVAX": "avalanche-2",
    "DOT": "polkadot", "MATIC": "matic-network", "LINK": "chainlink", "UNI": "uniswap",
    "ATOM": "cosmos", "LTC": "litecoin", "BCH": "bitcoin-cash", "FIL": "filecoin",
    "APT": "aptos", "OP": "optimism", "ARB": "arbitrum", "SUI": "sui",
    "TRX": "tron", "SHIB": "shiba-inu", "PEPE": "pepe", "TON": "the-open-network",
    "NEAR": "near", "ICP": "internet-computer",
}


def _resolve_coin_id(symbol: str) -> Optional[str]:
    # 先查靜態對照表，找不到再呼叫 CoinGecko 的 search 端點
    import requests

    s = symbol.upper()
    if s in _COIN_IDS:
        return _COIN_IDS[s]
    try:
        resp = requests.get(COINGECKO_SEARCH, params={"query": s}, headers=CG_HEADERS, timeout=10)
        resp.raise_for_status()
        for coin in resp.json().get("coins", []):
            if coin.get("symbol", "").upper() == s:
                return coin["id"]
    except Exception:
        pass
    return None


def _get_crypto_price(symbol: str) -> str:
    # 查詢單一虛擬貨幣即時報價（美元＋台幣），含 24h 漲跌幅與市值
    import requests

    sym = symbol.strip().upper()
    coin_id = _resolve_coin_id(sym)
    if not coin_id:
        return f"找不到虛擬貨幣代號：{sym}（請用英文縮寫，如 BTC、ETH、SOL）"

    try:
        resp = requests.get(
            COINGECKO_PRICE, headers=CG_HEADERS,
            params={"ids": coin_id, "vs_currencies": "usd,twd", "include_24hr_change": "true",
                    "include_market_cap": "true", "include_24hr_vol": "true"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get(coin_id, {})
    except Exception as e:
        return f"虛擬貨幣查詢失敗（{sym}）：{e}"

    if not data:
        return f"查不到 {sym} 的報價資料"

    usd, twd, change_24h, market_cap, vol_24h = (
        data.get("usd"), data.get("twd"), data.get("usd_24h_change"),
        data.get("usd_market_cap"), data.get("usd_24h_vol"),
    )
    lines = [f"【{sym}】（{coin_id}）"]
    if usd is not None:
        usd_str = f"${usd:,.6f}" if usd < 1 else f"${usd:,.2f}"
        lines.append(f"現價：{usd_str} USD" + (f"  /  NT${twd:,.2f}" if twd else ""))
    if change_24h is not None:
        lines.append(f"24h 漲跌：{'▲' if change_24h >= 0 else '▼'} {abs(change_24h):.2f}%")
    if market_cap:
        lines.append(f"市值：${market_cap / 1e9:.2f}B USD")
    if vol_24h:
        lines.append(f"24h 成交量：${vol_24h / 1e6:.2f}M USD")
    return "\n".join(lines)


def _get_multiple_cryptos(symbols: str) -> str:
    # 一次查詢多個虛擬貨幣，逗號分隔，最多 10 個；先批次解析 coin ID 再一次查價格
    import requests

    tickers = [s.strip() for s in symbols.split(",") if s.strip()]
    if not tickers:
        return "請提供至少一個虛擬貨幣代號"
    if len(tickers) > 10:
        return "單次最多查詢 10 個幣種"

    id_map = {}
    for sym in tickers:
        cid = _resolve_coin_id(sym.upper())
        if cid:
            id_map[sym.upper()] = cid
    if not id_map:
        return "找不到任何符合的幣種代號"

    try:
        resp = requests.get(
            COINGECKO_PRICE, headers=CG_HEADERS,
            params={"ids": ",".join(id_map.values()), "vs_currencies": "usd", "include_24hr_change": "true"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"批次查詢失敗：{e}"

    results = []
    for sym, cid in id_map.items():
        row = data.get(cid, {})
        usd = row.get("usd")
        if usd is None:
            results.append(f"【{sym}】查無資料")
            continue
        usd_str = f"${usd:,.6f}" if usd < 1 else f"${usd:,.2f}"
        chg = row.get("usd_24h_change")
        arrow = f"  {'▲' if chg >= 0 else '▼'} {abs(chg):.2f}%" if chg is not None else ""
        results.append(f"【{sym}】{usd_str} USD{arrow}")
    return "\n".join(results)


def _get_exchange_rate(from_currency: str, to_currency: str = "TWD", amount: float = 1.0) -> str:
    # 查詢即時匯率並換算金額；to_currency 填 "ALL" 時回傳常用貨幣一覽
    import requests

    base, target = from_currency.strip().upper(), to_currency.strip().upper()
    try:
        resp = requests.get(ER_URL.format(base=base), timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"匯率查詢失敗：{e}"

    if data.get("result") != "success":
        return f"不支援的貨幣代碼：{base}（請使用 ISO 4217 代碼，如 USD、TWD、JPY）"

    rates = data.get("rates", {})
    if target == "ALL":
        lines = [f"【{base} 匯率一覽】"]
        for cur in ["TWD", "USD", "EUR", "JPY", "CNY", "HKD", "GBP", "KRW", "SGD", "AUD"]:
            rate = rates.get(cur)
            if rate:
                lines.append(f"  {base} → {cur}：{rate:.4f}（{amount} {base} = {rate * amount:.2f} {cur}）")
        return "\n".join(lines)

    rate = rates.get(target)
    if rate is None:
        return f"找不到 {target} 的匯率資料"
    lines = [
        f"【{base} → {target}】",
        f"匯率：1 {base} = {rate:.4f} {target}",
        f"換算：{amount} {base} = {rate * amount:,.4f} {target}",
    ]
    if data.get("time_last_update_utc"):
        lines.append(f"更新時間（UTC）：{data['time_last_update_utc']}")
    return "\n".join(lines)


class CryptoPriceTool(Tool):
    # 查詢單一虛擬貨幣即時報價
    name = "get_crypto_price"
    description = "查詢單一虛擬貨幣即時報價（美元＋台幣），含 24h 漲跌幅與市值。使用英文縮寫代號，如 BTC、ETH、SOL"
    parameters = {
        "type": "object",
        "properties": {"symbol": {"type": "string", "description": "虛擬貨幣縮寫，如 BTC、ETH、SOL"}},
        "required": ["symbol"],
    }

    def run(self, symbol: str, **kwargs) -> ToolResult:
        return ToolResult(output=_get_crypto_price(symbol))


class MultiCryptoTool(Tool):
    # 一次查詢多個虛擬貨幣
    name = "get_multiple_cryptos"
    description = "一次查詢多個虛擬貨幣報價，代號以逗號分隔，最多 10 個"
    parameters = {
        "type": "object",
        "properties": {"symbols": {"type": "string", "description": "逗號分隔，例如：BTC,ETH,SOL"}},
        "required": ["symbols"],
    }

    def run(self, symbols: str, **kwargs) -> ToolResult:
        return ToolResult(output=_get_multiple_cryptos(symbols))


class ExchangeRateTool(Tool):
    # 查詢即時匯率並換算金額
    name = "get_exchange_rate"
    description = "查詢即時匯率並換算金額。to_currency 填 ALL 可一次看常用貨幣一覽"
    parameters = {
        "type": "object",
        "properties": {
            "from_currency": {"type": "string", "description": "來源貨幣代碼，例如：USD、TWD"},
            "to_currency": {"type": "string", "description": "目標貨幣代碼，預設 TWD；填 ALL 看一覽"},
            "amount": {"type": "number", "description": "要換算的金額，預設 1"},
        },
        "required": ["from_currency"],
    }

    def run(self, from_currency: str, to_currency: str = "TWD", amount: float = 1.0, **kwargs) -> ToolResult:
        return ToolResult(output=_get_exchange_rate(from_currency, to_currency, amount))
