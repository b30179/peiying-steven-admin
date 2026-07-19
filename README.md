# 培英中學行政 AI 助手 (Steven Demo)

香港培英中學行政老師 AI 輔助系統 — 演示版。基於 Next.js + FastAPI + PostgreSQL 構建，支援文檔 OCR、AI 自動校對、合約管理、庫存盤點等行政辦公場景。

## 🏗️ 技術架構

| 層 | 技術 |
|---|---|
| 前端 | Next.js 16 + React + Tailwind CSS |
| 後端 | FastAPI (Python 3.11) / PostgreSQL 18 / Alembic |
| AI | Azure Document Intelligence (OCR) / AI 輔助寫作 |
| 部署 | Docker Compose / Caddy |

## 📁 項目結構

```
培英/
├── 00-項目規範/        設計規範與邊界
├── 01-當前方案/        最新方案文檔 (v4.6)
├── 02-實施任務/        分階段實施計劃與演示腳本
│   ├── 01-總規劃/
│   ├── 02-S1演示/      S1: 文檔 OCR 演示
│   ├── 03-S2持久化與OCR/ S2: 在線 OCR + 持久化
│   ├── 04-S3演示/      S3: 庫存盤點演示
│   ├── 05-安全收口/
│   ├── 06-演示與交付/
│   └── 07-架構/
├── 03-參考資料/        原始需求參考
├── 04-開發實現/        核心代碼
│   ├── apps/           API + Web 應用
│   ├── data/           種子數據與遷移
│   ├── scripts/        Demo 腳本與驗證
│   ├── infra/          Docker 配置
│   └── tools/          Caddy 反向代理
├── 05-測試驗收/        驗收證據
├── 90-審計記錄/        實施審計
└── 99-歷史歸檔/        歷史版本
```

## 🚀 快速啟動

### 前置要求

- Docker Desktop
- Python 3.11+
- Node.js 20+
- PostgreSQL 18

### 安裝

```bash
# 1. 克隆倉庫
git clone <repo-url>
cd 培英

# 2. 配置環境變量
cp .env.example .env
# 編輯 .env 填入實際值

# 3. 啟動數據庫
cd 04-開發實現
docker compose -f infra/docker-compose.postgres.yml up -d

# 4. 安裝依賴
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r apps/api/requirements.txt

cd apps/web
npm install

# 5. 運行遷移
cd ../..
python -m alembic upgrade head

# 6. 載入 Demo 數據
python scripts/reset_steven_demo_data.py

# 7. 啟動服務
python -m uvicorn app.main:app --reload  # 後端 :8000
cd apps/web && npm run dev                # 前端 :3000
```

## 📦 交付包

便攜演示包請從 [GitHub Releases](../../releases) 下載 `Steven_Portable_Demo.zip`，解壓即用。

## 🔒 安全說明

- 所有密碼通過環境變量 `.env` 管理，**不要提交 `.env` 到版本控制**
- Demo 密碼僅為開發測試用途，生產環境請更換
- API Key 請通過環境變量 `AI_SERVICE_API_KEY` 設置

---

## 📖 更多文檔

本項目含多個 README，各有分工：

| 文件 | 說明 |
|---|---|
| `README.md`（本文件） | 項目大門 — 概覽、架構、快速啟動 |
| [`04-開發實現/README.md`](04-開發實現/README.md) | **技術細節** — 模塊狀態、驗收記錄、API 說明 |
| `04-開發實現/tools/caddy/README.md` | Caddy 反向代理配置 |
| `05-測試驗收/README.md` | 測試驗收說明 |

## 📄 許可

本項目為香港培英中學行政 AI 助手演示版，僅供參考與學習用途。
