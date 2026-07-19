# Steven S2 採購比價：Next.js + TypeScript 實作說明

## 路由與檔案結構

採用 App Router，主頁面為 `/dashboard/steven/quotes`。Steven 是唯一入口，不建立其他職能、供應商搜尋、自動審批或下單路徑。

```text
app/dashboard/steven/quotes/
  page.tsx                         # 事項列表
  [quoteId]/page.tsx               # 事項詳情
  components/
    QuotesPageHeader.tsx            # 唯一主操作：新建採購事項
    QuoteListTable.tsx              # 事項清單與篩選
    QuoteDetailHeader.tsx
    QuoteSummary.tsx
    QuoteMatrix.tsx                 # 3 家 x 5 品項矩陣
    SupplierQuoteCards.tsx          # 供應商級運費、稅費及有效期
    ImportPreflightDrawer.tsx
    ExceptionDrawer.tsx
    AttachmentDrawer.tsx
    AuditDrawer.tsx
    VersionDrawer.tsx
    RecommendationDialog.tsx
    ExportConfirmDialog.tsx
    ToastRegion.tsx
  lib/
    quote-calculations.ts           # 可重現、無副作用的排序與阻斷計算
    quote-validation.ts             # 導入預檢及人工推薦欄位規則
  types/quotes.ts
```

## 核心型別與計算責任

```ts
export type Currency = 'HKD' | 'USD';
export type Severity = 'blocking' | 'warning';
export type Recommendation = {
  supplierId: string | null;
  note: string;
  nonLowestReason: string;
  approvalOpinion: string;
  savedAt?: string;
};

export type QuoteLine = {
  itemId: string;
  supplierId: string;
  unitPrice: number | null;
  currency: Currency;
  validUntil: string | null;
};

export type SupplierCharge = {
  supplierId: string;
  shipping: number;
  tax: number;
};

export type PreflightIssue = {
  line: number;
  field: string;
  severity: Severity;
  message: string;
};
```

`getSupplierTotals()` 先加總該供應商的所有有效單價，再只加一次 `shipping` 和 `tax`。`rankPrices()` 僅回傳可顯示的系統排序與計算依據；它不能寫入 `Recommendation`。`getComparisonBlockers()` 在任一缺報價、幣種不一致或無效期報價存在時回傳阻斷原因。系統永遠不選供應商、不送審、不建立訂單或通知。

## 建議狀態模型

Server state 由後端讀寫並以 React Query 或 Server Actions 重新驗證；暫態 UI state 可由頁面容器管理：

```ts
type QuotesUiState = {
  activeDrawer: 'import' | 'exceptions' | 'attachments' | 'audit' | 'versions' | null;
  dialog: 'recommend' | 'export' | null;
  importAcknowledged: boolean;
  preflightIssues: PreflightIssue[];
  recommendationDraft: Recommendation;
  toast: { kind: 'success' | 'error'; message: string } | null;
};
```

- 導入：檔案上傳後產生不可忽略的 `PreflightIssue[]`；有 `blocking` 問題時，確認寫入按鈕必須禁用或回報未寫入。
- 推薦：`supplierId` 初始值必為 `null`。當選中的供應商不是 `rankPrices()` 第一名時，`nonLowestReason` 與 `approvalOpinion` 都是必填欄位。
- 導出：`ExportConfirmDialog` 顯示下一版號，確認後呼叫 `createExcelVersion(quoteId)`。後端以 append-only 方式建立 `v(n+1)`，不得覆蓋或刪除歷史版本。
- 審計：對導入確認、異常處理、推薦儲存、導出確認建立不可變更的 actor、時間、動作與前後摘要記錄。

## Props 邊界

`QuoteListTable` 接收 `quotes`、`filters`、`onFiltersChange` 和 `onOpenQuote`；不持有業務計算。`QuoteMatrix` 接收標準品項、`QuoteLine[]`、`SupplierCharge[]` 及純計算結果。`SupplierQuoteCards` 只呈現供應商級狀態與一次性費用。所有 Drawer 接收 `open`、`onOpenChange`，導入元件另接收 `onConfirmWrite`。`RecommendationDialog` 接收 `rankedSupplierId` 及 `onSave(draft)`，不自行推定預設供應商。

## 響應式行為

- `>= 1024px`：詳情採主內容 + 330px 供應商摘要欄，矩陣可完整橫向閱讀。
- `768px–1023px`：供應商摘要移到矩陣下方；列表保留橫向捲動容器，欄位不壓縮。
- `< 768px`：頁首主操作全寬；統計資訊為 2 欄；詳情操作按鈕折行；抽屜全寬。表格維持可橫向捲動，避免資料欄位被截斷或轉換成難掃描卡片。

## 無障礙與互動

- 所有抽屜與對話框使用 `role="dialog"`、`aria-modal="true"`、標題關聯與焦點陷阱；Escape 和遮罩可關閉並把焦點還給觸發按鈕。
- 導入預檢表列使用可讀行號、欄位、嚴重程度；阻斷訊息不只依賴紅色。
- 推薦表單錯誤以 `aria-describedby` 與 `aria-live="polite"` 宣告，且提供具體修正文字。
- Toast 使用 `role="status"`，不打斷鍵盤操作。表格加上 caption 或可見標題及正確 `<th scope>`。
- 主要按鈕、Icon button 與控制項保證最少 40–44px 可點擊區，提供 `:focus-visible` 樣式與 disabled 狀態。

## 安全與流程限制

頁面只處理人工輸入、人工覆核、排序和版本化導出。不得接入 AI/OCR、供應商搜尋、推薦自動填寫、審批、下單、郵件或任何外部執行動作。後端同樣必須在 API 層強制這些限制，不能只依賴前端隱藏按鈕。
