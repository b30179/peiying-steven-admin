# 🏫 培英中學 Steven 行政 AI 助手

> 為香港培英中學行政老師打造的 AI 輔助辦公系統 —— 文檔智能 OCR、標書校對、採購比價、庫存盤點，一站式搞定。

## ✨ 能做什么

- 📄 **文檔 OCR** — 掃描件/PDF 自動提取文字，支援繁體中文
- 🤖 **AI 標書校對** — DeepSeek 輔助校對招標文書，結果人工審核後才入庫
- 📊 **採購比價** — 多供應商比價、Excel 導出、AI 分析輔助推薦
- 📦 **庫存盤點** — Excel 批量導入、智能列映射、低庫存預警、自然語言錄入
- 🔐 **安全底座** — RBAC 權限、CSRF 防護、審計日誌、脫敏 Demo 數據

## 🚀 快速開始

```bash
# 1. 啟動數據庫
docker compose -f 04-開發實現/infra/docker-compose.postgres.yml up -d

# 2. 安裝依賴
cd 04-開發實現/apps/api && pip install -r requirements.txt
cd 04-開發實現/apps/web && npm install

# 3. 初始化 & 啟動
cp .env.example .env          # 編輯環境變量
python -m alembic upgrade head  # 數據庫遷移
python scripts/reset_steven_demo_data.py  # 載入 Demo 數據
python -m uvicorn app.main:app --reload &  # 後端 :8000
cd apps/web && npm run dev                  # 前端 :3000
```

> 📦 **不想自己裝？** 直接下載 [便攜 Demo 包](https://github.com/b30179/peiying-steven-admin/releases/latest)，解壓即用。

## 🧱 技術棧

| 層 | 技術 |
|---|---|
| 前端 | Next.js 16 · React · Tailwind CSS · TypeScript |
| 後端 | FastAPI · Python 3.11 · Alembic |
| 數據 | PostgreSQL 18 |
| OCR | PaddleOCR (離線) |
| AI | DeepSeek (僅校對/結構化，不自動決策) |
| 安全 | RBAC · CSRF · Argon2 · 審計日誌 |

## 📁 目錄

```
├── README.md                 ← 你在這裡
├── 00-項目規範/              設計邊界與約定
├── 01-當前方案/              最新方案文檔
├── 02-實施任務/              分階段計劃與演示腳本
│   ├── 01-總規劃/            總體規劃與交付清單
│   ├── 02-S1演示/            S1 文檔 OCR 演示
│   ├── 03-S2持久化與OCR/     S2 在線 OCR + 持久化
│   ├── 04-S3演示/            S3 庫存盤點演示
│   ├── 05-安全收口/          安全加固實施
│   ├── 06-演示與交付/        演示腳本與用戶手冊
│   └── 07-架構/              全業務復用架構
├── 04-開發實現/              ⭐ 源碼入口
│   ├── apps/api/             FastAPI 後端
│   ├── apps/web/             Next.js 前端
│   ├── scripts/              Demo 腳本
│   └── infra/                Docker 配置
├── 05-測試驗收/              驗收證據
└── 99-歷史歸檔/              歷史版本
```

## 📖 深入閱讀

- **[技術詳情](04-%E5%BC%80%E5%8F%91%E5%AE%9E%E7%8E%B0/README.md)** — 模塊狀態、驗收記錄、API 說明、遷移鏈
- **[用戶操作手冊](02-%E5%AE%9E%E6%96%BD%E4%BB%BB%E5%8A%A1/06-%E6%BC%94%E7%A4%BA%E4%B8%8E%E4%BA%A4%E4%BB%98/Steven_%E7%94%A8%E6%88%B7%E6%93%8D%E4%BD%9C%E6%89%8B%E5%86%8C_v1_2026-07-17.md)**
- **[交付清單](02-%E5%AE%9E%E6%96%BD%E4%BB%BB%E5%8A%A1/01-%E6%80%BB%E8%A7%84%E5%88%92/Steven_%E4%BA%A4%E4%BB%98%E6%B8%85%E5%8D%95_v1_2026-07-17.md)**

## ⚠️ 重要說明

本項目為 **脫敏 Demo 版本**，AI 輸出均進入人工審核層，不自動決定供應商、預算、審批或下單。非生產環境，不含真實業務數據。

---

*香港培英中學 Steven 崗位行政 AI 助手 · Demo v1.0 · 僅供參考與學習用途*
