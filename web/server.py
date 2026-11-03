"""byte_town 的控制面板後端（FastAPI）。

這不是另外做一套跑 agent 的邏輯，純粹是「透過網頁操作現有的 CLI」：
每個 agent 本來就是 python 0X_xxx/run_agent.py "任務" 這樣跑，這裡只是
改成用 subprocess 幫使用者按下按鈕時自動執行同一條指令，狀態跟歷史
則直接讀 RunLogger（common/logging_utils.py）跟 SessionStore（common/memory）
已經在寫的 data/logs/、data/memory/sessions/，不另外維護一份資料。

好處：完全不用改動任何一個 agent 既有的程式碼就能上線；壞處：目前沒有
「同一個 agent 同時只能跑一個任務」以外的併發保護（例如兩個不同 agent
同時寫同一個檔案），這跟現在手動開兩個終端機跑是一樣的風險，不是這次
新增的問題。

啟動方式： python web/server.py，然後瀏覽器打開 http://127.0.0.1:8000
"""
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from common.memory import build_default_memory  # noqa: E402

DATA_DIR = ROOT_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
MEMORY_DIR = DATA_DIR / "memory"

# 7 個 agent 的基本資料：id 給網頁跟 API 用，folder 對應資料夾名稱，
# label 是顯示用的名稱，跟 RunLogger 寫檔時用的 agent_name（= label 去掉括號說明）要對得上，
# 否則 _find_log_file() 會找不到對應的 log 檔
AGENTS = [
    {"id": "pip", "folder": "00_manager_pip", "name": "Pip", "label": "Pip（管理者，可自動分配給其他 agent）"},
    {"id": "scout", "folder": "01_researcher_scout", "name": "Scout", "label": "Scout（研究者）"},
    {"id": "owl", "folder": "02_analyst_owl", "name": "Owl", "label": "Owl（分析師）"},
    {"id": "bolt", "folder": "03_coder_bolt", "name": "Bolt", "label": "Bolt（程式開發者）"},
    {"id": "quill", "folder": "04_writer_quill", "name": "Quill", "label": "Quill（寫手）"},
    {"id": "ash", "folder": "05_reviewer_ash", "name": "Ash", "label": "Ash（審核者）"},
    {"id": "moss", "folder": "06_librarian_moss", "name": "Moss", "label": "Moss（圖書館員）"},
]
AGENTS_BY_ID = {a["id"]: a for a in AGENTS}

# 記錄每個 agent 目前執行中的 subprocess，key 是 agent id；
# 只存在記憶體裡，重啟網頁後端就會遺失追蹤（但 log 檔跟 session 存檔不會丟）
RUNS: dict[str, dict] = {}

app = FastAPI(title="Byte Town 控制面板")


class RunRequest(BaseModel):
    agent_id: str
    task: str


def _find_log_file(agent_name: str, started_at: float) -> Optional[Path]:
    # 在 data/logs 裡找這次執行對應的 log 檔：篩出檔名以 agent_name 開頭、
    # 修改時間不早於啟動時間（留 2 秒緩衝給檔案系統時間精度誤差）的最新一個
    candidates = sorted(LOG_DIR.glob(f"{agent_name}_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    for c in candidates:
        if c.stat().st_mtime >= started_at - 2:
            return c
    return None


def _tail(path: Path, max_chars: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return ""
    return text if len(text) <= max_chars else "…（前面省略）\n" + text[-max_chars:]


def _agent_status(agent: dict) -> dict:
    run = RUNS.get(agent["id"])
    running = False
    if run is not None:
        running = run["proc"].poll() is None
        if not running:
            # 程序已經結束，清掉 returncode 讓前端知道上一輪是否正常結束
            run["returncode"] = run["proc"].returncode

    log_path = None
    if run is not None:
        log_path = run.get("log_path") or _find_log_file(agent["name"], run["started_at"])
        if log_path and not run.get("log_path"):
            run["log_path"] = log_path

    session_store, _ = build_default_memory(MEMORY_DIR)
    recent = session_store.list_sessions(agent_name=agent["name"], limit=1)
    last_session = recent[0] if recent else None

    # _meta.json 只存 task/created_at（給清單用，故意不存完整對話省空間），
    # 完整回答要另外打開該次 session 的 JSON 檔才讀得到
    last_answer = None
    if last_session:
        full = session_store.load(last_session["session_id"])
        if full:
            last_answer = full.get("answer")

    return {
        "id": agent["id"],
        "label": agent["label"],
        "running": running,
        "current_task": run["task"] if run else None,
        "returncode": run.get("returncode") if run else None,
        "log_tail": _tail(log_path) if log_path else "",
        "last_session": last_session,
        "last_answer": last_answer,
    }


@app.get("/api/status")
def get_status():
    return [_agent_status(a) for a in AGENTS]


@app.get("/api/sessions")
def get_sessions(agent_id: Optional[str] = None, limit: int = 20):
    agent_name = AGENTS_BY_ID[agent_id]["name"] if agent_id else None
    session_store, _ = build_default_memory(MEMORY_DIR)
    return session_store.list_sessions(agent_name=agent_name, limit=limit)


@app.post("/api/run")
def run_agent(req: RunRequest):
    agent = AGENTS_BY_ID.get(req.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"未知的 agent：{req.agent_id}")
    if not req.task.strip():
        raise HTTPException(status_code=400, detail="任務內容不能是空的")

    existing = RUNS.get(req.agent_id)
    if existing is not None and existing["proc"].poll() is None:
        raise HTTPException(status_code=409, detail=f"{agent['name']} 目前還在執行上一個任務，請等它完成")

    script = ROOT_DIR / agent["folder"] / "run_agent.py"
    # 跟使用者手動在終端機打 python 0X_xxx/run_agent.py "任務" 完全一樣的指令，
    # 只是這裡用程式自動幫忙按下 Enter；stdout/stderr 導去 DEVNULL 是因為
    # 真正的執行過程已經即時寫進 RunLogger 的 log 檔，不需要再額外保留一份
    proc = subprocess.Popen(
        [sys.executable, str(script), req.task],
        cwd=str(ROOT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    RUNS[req.agent_id] = {"proc": proc, "task": req.task, "started_at": time.time(), "log_path": None}
    return {"ok": True, "pid": proc.pid}


@app.post("/api/stop/{agent_id}")
def stop_agent(agent_id: str):
    run = RUNS.get(agent_id)
    if run is None or run["proc"].poll() is not None:
        raise HTTPException(status_code=404, detail="目前沒有正在執行中的任務")
    run["proc"].terminate()
    try:
        run["proc"].wait(timeout=5)
    except subprocess.TimeoutExpired:
        run["proc"].kill()  # terminate 5 秒內沒反應就強制結束
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(Path(__file__).resolve().parent / "static" / "index.html")


if __name__ == "__main__":
    import uvicorn

    # 只綁 127.0.0.1：這是本機操作面板，不對外網公開
    uvicorn.run(app, host="127.0.0.1", port=8000)
