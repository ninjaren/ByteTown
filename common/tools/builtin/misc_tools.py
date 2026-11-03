"""移植自 qwen3_4b/tools/utils.py。

去耦合：QRCodeTool 的輸出目錄原本寫死成 F:\\python_project\\ai_agent\\data\\qrcodes，
改成建構時傳入 output_dir（預設落在呼叫端自己的 workspace 下）。
"""
from datetime import datetime
from pathlib import Path
from typing import Union

from ..base import Tool, ToolResult

# ip-api.com 免費端點，不需 Key，每分鐘 45 次限制
IP_API_URL = (
    "http://ip-api.com/json/{ip}?lang=zh-TW"
    "&fields=status,message,country,regionName,city,isp,org,timezone,lat,lon,query"
)


class ClipboardTool(Tool):
    # 讓使用者可以直接貼文字進對話，不用重複貼一次
    name = "read_clipboard"
    description = "讀取使用者系統剪貼簿的文字內容"
    parameters = {"type": "object", "properties": {}}

    def run(self, **kwargs) -> ToolResult:
        try:
            import pyperclip
        except ImportError:
            return ToolResult(output=None, error="缺少 pyperclip 套件，請先執行：pip install pyperclip")
        try:
            text = pyperclip.paste()
        except Exception as e:
            return ToolResult(output=None, error=f"讀取剪貼簿失敗：{e}")
        if not text:
            return ToolResult(output="剪貼簿目前是空的")
        preview = text[:200] + f"\n...（以下省略 {len(text) - 200} 字）" if len(text) > 200 else text
        return ToolResult(output=f"【剪貼簿內容】（共 {len(text)} 字）\n{preview}")


class QRCodeTool(Tool):
    # 產生 QR Code PNG 並存到 output_dir，回傳圖片路徑，可搭配 analyze_image 確認內容
    name = "create_qr_code"
    description = "將文字或網址產生成 QR Code PNG 圖片，回傳圖片路徑"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要編碼的文字或網址"},
            "filename": {"type": "string", "description": "輸出檔名（不含路徑，留空自動產生）"},
        },
        "required": ["text"],
    }

    def __init__(self, output_dir: Union[str, Path]):
        self._output_dir = Path(output_dir)

    def run(self, text: str, filename: str = "", **kwargs) -> ToolResult:
        try:
            import qrcode
        except ImportError:
            return ToolResult(output=None, error="缺少 qrcode 套件，請先執行：pip install qrcode[pil]")
        try:
            qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
            qr.add_data(text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            self._output_dir.mkdir(parents=True, exist_ok=True)
            if filename:
                safe_name = Path(filename).stem + ".png"  # 去掉副檔名再補 .png，避免重複
            else:
                safe_name = f"qr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            out_path = self._output_dir / safe_name
            img.save(str(out_path))
            return ToolResult(output=str(out_path))
        except Exception as e:
            return ToolResult(output=None, error=f"QR Code 產生失敗：{e}")


class IPInfoTool(Tool):
    # 查詢 IP 地理位置資訊（ISP、國家、城市、時區），不填 ip 則查詢本機對外公網 IP
    name = "get_ip_info"
    description = "查詢 IP 位址的地理位置、ISP 業者與時區資訊，不填 ip 則查詢本機對外 IP"
    parameters = {
        "type": "object",
        "properties": {"ip": {"type": "string", "description": "要查詢的 IP 位址，留空查詢本機 IP"}},
    }

    def run(self, ip: str = "", **kwargs) -> ToolResult:
        import requests

        url = IP_API_URL.format(ip=ip.strip())
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return ToolResult(output=None, error=f"IP 查詢失敗：{e}")

        if data.get("status") != "success":
            return ToolResult(output=None, error=f"IP 查詢失敗：{data.get('message', '未知錯誤')}")

        lines = [
            f"【IP 資訊】{data.get('query', ip or '本機 IP')}",
            f"位置：{data.get('country', 'N/A')} > {data.get('regionName', 'N/A')} > {data.get('city', 'N/A')}",
            f"ISP：{data.get('isp', 'N/A')}",
            f"時區：{data.get('timezone', 'N/A')}",
            f"座標：{data.get('lat', 'N/A')}, {data.get('lon', 'N/A')}",
        ]
        return ToolResult(output="\n".join(lines))
