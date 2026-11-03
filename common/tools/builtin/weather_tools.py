"""移植自 qwen3_4b/tools/weather.py，純功能無狀態，原樣搬入（wttr.in，免 API Key）。"""
from urllib.parse import quote

from ..base import Tool, ToolResult

WTTR_URL = "https://wttr.in/{location}?format=j1&lang=zh-tw"

_WEATHER_ZH = {
    "Sunny": "晴天", "Clear": "晴朗", "Partly cloudy": "晴時多雲",
    "Cloudy": "多雲", "Overcast": "陰天", "Mist": "薄霧", "Fog": "霧",
    "Light rain": "小雨", "Moderate rain": "中雨", "Heavy rain": "大雨",
    "Light drizzle": "毛毛雨", "Freezing drizzle": "凍雨",
    "Patchy rain nearby": "局部有雨", "Patchy rain possible": "局部可能有雨",
    "Thundery outbreaks possible": "可能有雷陣雨",
    "Blowing snow": "吹雪", "Light snow": "小雪", "Moderate snow": "中雪",
    "Heavy snow": "大雪", "Blizzard": "暴風雪",
    "Light sleet": "小凍雨", "Moderate or heavy sleet": "中到大凍雨",
    "Light showers of ice pellets": "輕度冰雹", "Ice pellets": "冰雹",
}


def _zh_desc(desc: str) -> str:
    return _WEATHER_ZH.get(desc, desc)


def _get_weather(location: str) -> str:
    import requests

    try:
        resp = requests.get(
            WTTR_URL.format(location=quote(location)),
            headers={"User-Agent": "curl/7.68.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"天氣查詢失敗：{e}"

    try:
        cur, today = data["current_condition"][0], data["weather"][0]
        astro = today["astronomy"][0]
        lang_key = "lang_zh-tw"
        en_desc = cur["weatherDesc"][0]["value"]
        desc = _zh_desc(en_desc) if en_desc in _WEATHER_ZH else (cur.get(lang_key, [{}])[0].get("value") or en_desc)

        lines = [
            f"【{location}】目前天氣",
            f"天氣狀況：{desc}",
            f"氣溫：{cur['temp_C']}°C（體感 {cur['FeelsLikeC']}°C）",
            f"今日最高／最低：{today['maxtempC']}°C／{today['mintempC']}°C",
            f"濕度：{cur['humidity']}%　風向：{cur['winddir16Point']}　風速：{cur['windspeedKmph']} km/h",
            f"UV 指數：{cur.get('uvIndex', 'N/A')}　能見度：{cur.get('visibility', 'N/A')} km",
            f"日出：{astro['sunrise']}　日落：{astro['sunset']}",
        ]

        hourly = today.get("hourly", [])
        if hourly:
            lines.append("\n逐時預報：")
            for h in hourly:
                t = int(h["time"]) // 100
                h_en = h["weatherDesc"][0]["value"]
                h_desc = _zh_desc(h_en) if h_en in _WEATHER_ZH else (h.get(lang_key, [{}])[0].get("value") or h_en)
                lines.append(f"  {t:02d}:00　{h['tempC']}°C　{h_desc}　降雨機率 {h.get('chanceofrain', '0')}%")

        if len(data["weather"]) >= 3:
            lines.append("\n未來天氣：")
            for day in data["weather"][1:3]:
                raw_desc = day["hourly"][4]["weatherDesc"][0]["value"] if day.get("hourly") else ""
                d_desc = (day["hourly"][4].get(lang_key, [{}])[0].get("value") or _zh_desc(raw_desc)) if day.get("hourly") else ""
                lines.append(f"  {day['date']}　最高 {day['maxtempC']}°C / 最低 {day['mintempC']}°C　{d_desc}")

        return "\n".join(lines)
    except (KeyError, IndexError) as e:
        return f"天氣資料解析失敗：{e}（原始回應可能格式異常）"


class WeatherTool(Tool):
    # 查詢指定地點的目前天氣與今日/未來預報，支援中文城市、英文或機場代碼
    name = "get_weather"
    description = "查詢指定地點的目前天氣、今日溫度範圍、濕度、風速、UV 指數與未來兩天預報"
    parameters = {
        "type": "object",
        "properties": {"location": {"type": "string", "description": "地點，例如：台北、高雄、Tokyo"}},
        "required": ["location"],
    }

    def run(self, location: str, **kwargs) -> ToolResult:
        return ToolResult(output=_get_weather(location))
