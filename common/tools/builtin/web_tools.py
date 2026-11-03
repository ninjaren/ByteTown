"""移植自 qwen3_4b/tools/web.py。

去耦合：browse_url 原本用模組層級全域變數記錄「每個網域訪問次數」與
「上次訪問時間」，多個 agent 同時跑會共用同一份全域狀態、互相影響。
改成 BrowseUrlTool 自己持有這份狀態（_RateLimiter），每個 agent 各自一份，
需要在對話開始時重置就呼叫 tool.rate_limiter.reset()。
"""
import re
import threading
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

from ..base import Tool, ToolResult

DOMAIN_BLACKLIST = {"facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com"}

_JS_MARKERS = [
    "__NEXT_DATA__", "__NUXT__", "window.__INITIAL_STATE__",
    "data-reactroot", "ng-version", "data-vue", "__REACT_",
    "ReactDOM.render", "window.__data", "window.App",
]


def _extract_domain(url: str) -> str:
    # 從完整 URL 擷取網域，移除 www. 前綴方便做黑名單比對
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return url


def _is_blacklisted(domain: str) -> bool:
    # 完整網域或子網域都算在黑名單內
    return any(domain == b or domain.endswith("." + b) for b in DOMAIN_BLACKLIST)


def _is_js_rendered(html: str, text: str) -> bool:
    # 判斷此頁面是否為 JS 動態渲染的空殼（靜態 GET 拿不到實際內容）
    # 邏輯：HTML 夠大（不是空頁）但提取到的文字極少，才算是空殼；
    # 若文字已足夠（≥300 字），即使有 JS 框架標記也代表 SSR 有給出內容，不誤判
    text_stripped = text.strip()
    if len(html) < 2000:
        return False
    if len(text_stripped) >= 300:
        return False
    return any(m in html for m in _JS_MARKERS) or len(text_stripped) < 100


class _RateLimiter:
    """每個 BrowseUrlTool instance 自己的網域訪問計數器，不再是模組全域變數。"""

    def __init__(self, max_per_domain: int = 5, delay_seconds: float = 1.0):
        self.max_per_domain = max_per_domain
        self.delay_seconds = delay_seconds
        self._counts: dict = defaultdict(int)
        self._last_time: float = 0.0
        self._lock = threading.Lock()

    def reset(self) -> None:
        # 每次新對話開始時呼叫，重設各網域的訪問計數器
        with self._lock:
            self._counts.clear()

    def check_and_wait(self, domain: str) -> Optional[str]:
        # 先檢查並累計次數，超過上限就拒絕
        with self._lock:
            if self._counts[domain] >= self.max_per_domain:
                return f"拒絕訪問：{domain} 本次對話已訪問 {self.max_per_domain} 次，已達上限"
            self._counts[domain] += 1

        # 刻意用獨立的 with _lock 區塊：若在同一區塊內 sleep，鎖會在 sleep 期間
        # 持續被持有，導致其他執行緒完全無法讀寫計數器
        with self._lock:
            elapsed = time.time() - self._last_time
            if elapsed < self.delay_seconds:
                time.sleep(self.delay_seconds - elapsed)
            self._last_time = time.time()
        return None


class SearchWebTool(Tool):
    # 用 DuckDuckGo 搜尋，不需要 API Key，適合本機輕量使用
    name = "search_web"
    description = "用關鍵字搜尋網路，回傳多筆結果的標題、摘要與網址。若摘要不夠詳細，可用 browse_url 讀取網頁完整內容"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "搜尋關鍵字，越精確越好"}},
        "required": ["query"],
    }

    def run(self, query: str, **kwargs) -> ToolResult:
        try:
            from ddgs import DDGS
        except ImportError:
            return ToolResult(output=None, error="缺少 ddgs 套件，請先執行：pip install ddgs")

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return ToolResult(output="沒有找到相關結果，請換個關鍵字")
        return ToolResult(output="\n\n".join(
            f"[{i + 1}] 標題: {r['title']}\n    摘要: {r['body']}\n    網址: {r['href']}"
            for i, r in enumerate(results)
        ))


class BrowseUrlTool(Tool):
    # 抓取網頁並移除 HTML 標籤，回傳純文字（最多 5000 字）；內建速率限制、黑名單過濾、JS 動態渲染偵測
    name = "browse_url"
    description = "讀取指定網址的完整網頁內容，適合在搜尋後想深入閱讀某篇文章時使用。每個網域每次對話最多讀取 5 次"
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "要讀取的網頁網址"}},
        "required": ["url"],
    }

    def __init__(self, max_per_domain: int = 5, delay_seconds: float = 1.0):
        self.rate_limiter = _RateLimiter(max_per_domain, delay_seconds)

    def run(self, url: str, **kwargs) -> ToolResult:
        import requests

        domain = _extract_domain(url)
        if _is_blacklisted(domain):
            return ToolResult(output=f"拒絕訪問：{domain} 在黑名單中")

        limit_msg = self.rate_limiter.check_and_wait(domain)
        if limit_msg:
            return ToolResult(output=limit_msg)

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            html = resp.text

            # 移除 script、style 標籤，再去掉所有 HTML 標記，合併多餘空白
            text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html)
            text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            # JS 動態渲染空殼偵測：直接告訴模型要換策略，不依賴 system prompt
            if _is_js_rendered(html, text):
                return ToolResult(output=(
                    f"[JS渲染頁面] {url} 的內容需要 JavaScript 才能載入，直接讀取無法取得實際資料。"
                    f"請改用 search_web 搜尋相關新聞或文章。"
                ))
            return ToolResult(output=text[:5000] + ("…（內容截斷）" if len(text) > 5000 else ""))
        except Exception as e:
            return ToolResult(output=None, error=f"無法讀取網頁：{e}")


class FetchRssTool(Tool):
    # 解析 RSS 2.0 或 Atom feed；比 browse_url 更快更乾淨，且不易觸發反爬蟲機制
    name = "fetch_rss"
    description = "讀取 RSS 或 Atom feed，回傳最新文章的標題、日期、摘要與網址，比 browse_url 更快更乾淨"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "RSS 或 Atom feed 的網址"},
            "max_items": {"type": "integer", "description": "最多回傳幾筆，預設 10"},
        },
        "required": ["url"],
    }

    def run(self, url: str, max_items: int = 10, **kwargs) -> ToolResult:
        import requests

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            # 嘗試解析 RSS 2.0 格式：<rss><channel><item>
            items = []
            for item in root.findall(".//item")[:max_items]:
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                desc = re.sub(r"<[^>]+>", "", item.findtext("description", "")).strip()
                pub = item.findtext("pubDate", "").strip()
                items.append((title, link, desc[:200], pub))

            # 若 RSS 沒有結果，嘗試解析 Atom 格式：<feed><entry>
            if not items:
                atom = {"a": "http://www.w3.org/2005/Atom"}
                for entry in root.findall(".//a:entry", atom)[:max_items]:
                    title = entry.findtext("a:title", "", atom).strip()
                    link_el = entry.find("a:link", atom)
                    link = link_el.get("href", "") if link_el is not None else ""
                    summary = re.sub(r"<[^>]+>", "", entry.findtext("a:summary", "", atom)).strip()
                    pub = entry.findtext("a:published", "", atom).strip()
                    items.append((title, link, summary[:200], pub))

            if not items:
                return ToolResult(output="無法解析此 RSS/Atom feed，請確認網址正確")

            return ToolResult(output="\n\n".join(
                f"[{i + 1}] 標題: {t}\n    日期: {p}\n    摘要: {d}\n    網址: {l}"
                for i, (t, l, d, p) in enumerate(items)
            ))
        except Exception as e:
            return ToolResult(output=None, error=f"RSS 讀取失敗：{e}")


class ExtractLinksTool(Tool):
    # 從網頁抓出所有超連結，供模型決定下一步要深入哪幾篇（適合拿到新聞列表頁後先看有哪些文章）
    name = "extract_links"
    description = "從網頁中提取所有超連結，供進一步決定要深入閱讀哪幾篇"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要提取連結的網頁網址"},
            "max_links": {"type": "integer", "description": "最多回傳幾條連結，預設 20"},
        },
        "required": ["url"],
    }

    def run(self, url: str, max_links: int = 20, **kwargs) -> ToolResult:
        import requests

        domain = _extract_domain(url)
        if _is_blacklisted(domain):
            return ToolResult(output=f"拒絕訪問：{domain} 在黑名單中")

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()

            # 用正則擷取 href 與連結文字，過濾錨點（#）與相對路徑
            raw = re.findall(r'<a[^>]+href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>', resp.text, re.IGNORECASE | re.DOTALL)
            seen, links = set(), []
            for href, text in raw:
                href = urljoin(url, href.strip())  # 補全相對路徑
                if not href.startswith("http") or href in seen:
                    continue
                seen.add(href)
                text = re.sub(r"<[^>]+>", "", text).strip()[:50] or "（無文字）"
                links.append((text, href))
                if len(links) >= max_links:
                    break

            if not links:
                return ToolResult(output="此頁面未找到任何連結")
            return ToolResult(output=f"找到 {len(links)} 個連結：\n\n" + "\n".join(
                f"[{i + 1}] {t}\n    → {u}" for i, (t, u) in enumerate(links)
            ))
        except Exception as e:
            return ToolResult(output=None, error=f"連結提取失敗：{e}")
