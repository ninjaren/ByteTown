"""移植自 qwen3_4b/tools/github_trending.py 的 get_github_trending 部分。

去耦合：
- REPORT_DIR/SEEN_FILE 原本寫死路徑，改成建構時傳入 state_dir
- generate_weekly_report（會直接呼叫 Ollama 做批次翻譯，繞過 LLMProvider 抽象層）
  不搬過來，翻譯交給呼叫方的 agent 自己用 llm.generate() 處理，
  避免這個工具內部又綁死某一家 LLM
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Union

from ..base import Tool, ToolResult

TRENDING_URL = "https://github.com/trending?since=weekly"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def _week_id() -> str:
    # 回傳 ISO 週次字串，例如 2026-W42
    y, w, _ = datetime.now().isocalendar()
    return f"{y}-W{w:02d}"


def _parse_trending(html: str) -> list:
    # 解析 GitHub Trending 頁面 HTML，回傳最多 25 筆 repo 資料
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    repos = []
    for article in soup.select("article.Box-row"):
        try:
            link = article.select_one("h2 a, h1 a")
            if not link:
                continue
            repo_path = link.get("href", "").strip("/")
            if not repo_path or "/" not in repo_path:
                continue

            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""
            lang_el = article.select_one("[itemprop='programmingLanguage']")
            language = lang_el.get_text(strip=True) if lang_el else ""

            week_stars = 0
            for el in article.find_all(string=re.compile(r"stars?\s+this\s+week", re.I)):
                m = re.search(r"([\d,]+)\s+stars?\s+this\s+week", el, re.I)
                if m:
                    week_stars = int(m.group(1).replace(",", ""))
                    break

            total_stars = 0
            for a in article.select("a[href*='/stargazers']"):
                text = re.sub(r"[^\d]", "", a.get_text())
                if text.isdigit():
                    total_stars = int(text)
                    break

            repos.append({
                "repo": repo_path, "description": description, "language": language,
                "week_stars": week_stars, "total_stars": total_stars,
                "url": f"https://github.com/{repo_path}",
            })
        except Exception:
            continue
    return repos


class GithubTrendingTool(Tool):
    # 抓取 GitHub 本週熱門專案並標記是否重複上榜；描述保留英文原文，翻譯交給呼叫方的 agent 處理
    name = "get_github_trending"
    description = (
        "抓取 GitHub 本週熱門專案（依週增星數排名），回傳前 N 名的專案名稱、描述（英文原文）、"
        "語言、本週星星數與是否重複上榜。"
    )
    parameters = {
        "type": "object",
        "properties": {"count": {"type": "integer", "description": "要抓幾筆，預設 10，最多 25"}},
    }

    def __init__(self, state_dir: Union[str, Path]):
        # state_dir 存放「已出現過的 repo」紀錄，用來判斷是否連續上榜
        self._state_dir = Path(state_dir)
        self._seen_file = self._state_dir / "seen.json"

    def _load_seen(self) -> dict:
        # 讀取已出現過的 repo 紀錄（first_week + 每次出現的週次列表）
        if self._seen_file.exists():
            try:
                return json.loads(self._seen_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_seen(self, seen: dict) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._seen_file.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_seen(self, repos: list, week: str) -> list:
        # 更新 seen.json，並在每筆 repo 加入「首次上榜／連續上榜」的 badge 欄位
        seen = self._load_seen()
        for repo in repos:
            name = repo["repo"]
            if name not in seen:
                seen[name] = {"first_week": week, "weeks": [week]}
                repo["badge"] = "🆕 首次上榜"
            else:
                weeks_list = seen[name].get("weeks", [])
                if week not in weeks_list:
                    weeks_list.append(week)
                    seen[name]["weeks"] = weeks_list
                n = len(weeks_list)
                repo["badge"] = f"🔁 連續上榜 {n} 週" if n > 1 else "🆕 首次上榜"
        self._save_seen(seen)
        return repos

    def run(self, count: int = 10, **kwargs) -> ToolResult:
        # 抓取本週熱門專案，回傳結構化文字給 agent；描述為英文原文，由呼叫方的 LLM 翻譯
        import requests

        try:
            resp = requests.get(TRENDING_URL, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            return ToolResult(output=None, error=f"GitHub Trending 取得失敗：{e}")

        repos = _parse_trending(resp.text)
        if not repos:
            return ToolResult(output=None, error="無法解析 GitHub Trending 頁面（請確認已安裝：pip install beautifulsoup4）")

        week = _week_id()
        repos = self._update_seen(repos[:count], week)

        lines = [f"【GitHub 本週熱門專案】{week}（共 {len(repos)} 筆）\n"]
        for i, r in enumerate(repos, 1):
            lang = f"語言：{r['language']}　" if r["language"] else ""
            stars = f"⭐ 本週 +{r['week_stars']:,}" if r["week_stars"] else ""
            total = f"（共 {r['total_stars']:,}）" if r["total_stars"] else ""
            lines += [
                f"{i}. {r['badge']}  {r['repo']}",
                f"   {lang}{stars} {total}",
                f"   {r['description']}" if r["description"] else "",
                f"   🔗 {r['url']}",
                "",
            ]
        return ToolResult(output="\n".join(lines))
