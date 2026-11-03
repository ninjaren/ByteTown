# Byte Town

本地運行的多代理人（multi-agent）AI 系統：一個管理者 agent 協調 6 個專長各異的夥伴 agent，分工完成研究、分析、寫程式、寫作、審核、歸檔等任務，預設跑在本機 Ollama（qwen3:8b），也可以換成 Anthropic / OpenAI 等雲端模型。

## 7 個 Agent

| Agent | 角色 | 資料夾 |
|---|---|---|
| **Pip** | 管理者，判斷任務該交給誰，實際呼叫其他 agent 執行並整合回覆 | `00_manager_pip/` |
| **Scout** | 研究者，上網搜尋、讀網頁/RSS、讀 PDF、追蹤 GitHub 熱門專案 | `01_researcher_scout/` |
| **Owl** | 分析師，查股票/虛擬貨幣/匯率、畫走勢圖、數值計算 | `02_analyst_owl/` |
| **Bolt** | 程式開發者，讀寫檔案、列目錄、安全數學運算 | `03_coder_bolt/` |
| **Quill** | 寫手，撰寫/整理文章、報告、文件 | `04_writer_quill/` |
| **Ash** | 審核者，檢查程式碼或文件品質 | `05_reviewer_ash/` |
| **Moss** | 圖書館員，歸檔、查找、整理既有檔案與 CSV 資料 | `06_librarian_moss/` |

Pip 透過 `ask_scout` / `ask_owl` / `ask_bolt` / `ask_quill` / `ask_ash` / `ask_moss` 這些工具把子任務實際委派給對應的 agent 執行，不是只用文字描述分配方案；每個 agent 一樣會自己判斷要不要呼叫自己的工具。

## 架構特色

- **LLM-agnostic**：`common/llm/` 把不同 provider（Ollama／Anthropic／OpenAI）包成統一介面，每個 agent 只要改自己的 `config.yaml` 就能換模型
- **工具框架**：`common/tools/`，內建搜尋網路、讀寫檔案、股票/加密貨幣查價、畫圖表、讀 PDF、GitHub 趨勢等數十種工具（見 `common/tools/builtin/`）
- **Skill 系統**：每個 agent 的 `skills/*.yaml` 定義特定任務情境下的標準處理流程（prompt template + 限定工具），依任務內容關鍵字自動比對，沒命中就用模型自由發揮
- **Agentic loop**：`common/agent.py` 實作標準的「模型決定呼叫工具 → 執行 → 回傳結果 → 再讓模型判斷」迴圈，多輪直到給出最終答案
- **多代理人委派**：`common/tools/builtin/delegate_tool.py` 把「呼叫另一個 agent」包裝成普通工具，Pip 的 agentic loop 因此能像呼叫任何工具一樣委派任務
- **持久記憶**：`common/memory/`，每次任務存成 JSON session（`data/memory/sessions/`），另外用 ChromaDB 做語意向量記憶，Moss 可以查詢「之前有沒有人問過類似的事」
- **即時 log**：`common/logging_utils.py` 的 `RunLogger` 在執行過程中逐輪即時寫入 log（`data/logs/`），即使中途當掉也查得到卡在哪一步

## 網頁控制面板

`web/` 提供一個本機控制面板，可以即時查看 7 個 agent 的狀態、展開看執行 log 跟完整回答，也能直接從網頁送出任務：

```bash
python web/server.py
```

啟動後開瀏覽器打開 http://127.0.0.1:8000（只綁本機，不對外網公開）。面板純粹用 subprocess 幫你執行跟手動打 CLI 一樣的指令，不需要改動任何 agent 程式碼。

## 安裝

```bash
pip install -r requirements.txt
```

需要本機先跑起 [Ollama](https://ollama.com/) 並下載模型：

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text   # 語意記憶的 embedding 模型
```

若要改用雲端模型，複製 `.env.example` 成 `.env` 並填入對應的 API key，再把想換的 agent 的 `config.yaml` 裡 `llm.provider` / `llm.model` 改掉即可。

## 使用方式

直接執行單一 agent：

```bash
python 01_researcher_scout/run_agent.py "幫我查一下 byte_town 多代理人系統設計"
```

透過 Pip 自動判斷並委派給其他 agent：

```bash
python 00_manager_pip/run_agent.py "幫我查一下台積電(2330)目前股價"
```

或是啟動網頁控制面板，從瀏覽器選 agent、輸入任務、送出。

## 專案結構

```
00_manager_pip/        管理者 Pip
01_researcher_scout/   研究者 Scout
02_analyst_owl/        分析師 Owl
03_coder_bolt/         程式開發者 Bolt
04_writer_quill/       寫手 Quill
05_reviewer_ash/       審核者 Ash
06_librarian_moss/     圖書館員 Moss
common/                共用的 LLM 介面、工具框架、skill 系統、agentic loop、記憶模組
web/                   FastAPI 控制面板後端 + 前端頁面
data/                  執行期間自動產生（log、session、向量資料庫、下載快取），不進版控
```

每個 agent 資料夾底下都有 `run_agent.py`（執行入口）、`config.yaml`（模型設定）、`skills/`（該 agent 的技能定義）。
