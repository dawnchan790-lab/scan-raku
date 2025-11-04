# 発注スキャン集計 - 区切り職人1.5モジュール

発注書をスマホ/PCで撮影・選択し、日本語OCRで日付・品目・数量を自動抽出。品目別に集計してGoogleスプレッドシートへ保存し、A4印刷用PDFリンクを生成するMVPアプリケーションです。

## 📱 プロジェクト概要

- **名称**: 発注スキャン集計（MVP版）
- **目的**: 発注書の手入力作業を削減し、データ集計を自動化
- **対応端末**: iPhone Safari + PWA、Mac Safari/Chrome（HTTPS）
- **技術スタック**: 
  - バックエンド: Hono (Cloudflare Workers)
  - フロントエンド: Vanilla JavaScript + Tailwind CSS
  - OCR: Tesseract.js (日本語対応)
  - PWA: Service Worker + Manifest
  - 保存先: Google Apps Script → Googleスプレッドシート

## 🌐 公開URL

- **開発環境**: https://3000-ijw78ylivqr6nw947gbjz-ad490db5.sandbox.novita.ai
- **APIヘルスチェック**: https://3000-ijw78ylivqr6nw947gbjz-ad490db5.sandbox.novita.ai/api/health
- **GitHub**: （未設定）
- **本番環境**: （未デプロイ）

## ✨ 完成済み機能

### 1. 画像入力
- ✅ カメラ撮影（スマホ `capture="environment"`）
- ✅ ファイル選択（PC/スマホ）
- ✅ ドラッグ&ドロップ（PC）
- ✅ 画像プレビュー表示

### 2. 画像前処理
- ✅ EXIF向き補正
- ✅ 長辺2000pxリサイズ
- ✅ コントラスト強調
- ✅ 二値化（オプション実装）

### 3. OCR処理
- ✅ **Tesseract.js** による日本語OCR（デフォルト）
- ⚙️ Google Cloud Vision API対応（環境変数設定時に有効化）
- ✅ 処理進捗バーの表示

### 4. データ抽出
- ✅ 日付抽出
  - `YYYY/MM/DD`, `YYYY-MM-DD`, `YYYY年MM月DD日`
  - 令和表記対応（西暦自動変換）
  - `MM/DD` 形式（撮影年補完）
- ✅ 品目と数量抽出
  - 数量パターン: `(\d+(?:\.\d+)?)\s*(個|本|袋|箱|ケース|kg|g|玉|束|枚)?`
- ✅ 除外語フィルタ: `合計|小計|税込|税抜|計`
- ✅ テキスト正規化
  - 全角→半角変換
  - かな/カナ統一
  - トリム処理

### 5. UI編集機能
- ✅ 抽出結果のテーブル表示
- ✅ 品目名・数量・単位・備考の編集
- ✅ 行の追加/削除
- ✅ 品目別合計サマリーの自動計算
- ✅ 発注日の編集

### 6. Google Apps Script連携
- ✅ JSON形式でPOST送信
  ```json
  {
    "order_date": "YYYY-MM-DD",
    "lines": [{"item": "きゅうり", "qty": 12, "unit": "袋", "note": ""}],
    "totals": [{"item": "きゅうり", "qty": 12}],
    "source": {"image_name": "IMG_0001.jpg", "ocr_engine": "tesseract", "confidence": 0.85}
  }
  ```
- ✅ カスタムヘッダー: `X-APP-TOKEN`
- ✅ レスポンス処理: `sheetUrl`, `pdfUrl` 表示

### 7. オフライン対応
- ✅ Service Worker によるキャッシュ戦略
- ✅ IndexedDB による未送信データの保存
- ✅ オンライン復帰時の自動再送信

### 8. PWA対応
- ✅ `manifest.webmanifest` 設定
- ✅ iOS Safari対応メタタグ
- ✅ アイコン画像（192x192, 512x512）
- ✅ Service Worker登録

### 9. 設定管理
- ✅ Google Apps Script URL設定
- ✅ アプリトークン設定
- ✅ LocalStorageへの永続化

## 🚧 未実装機能

- ❌ Google Cloud Vision API の有効化（APIキー設定が必要）
- ❌ 台形補正（現在は未実装）
- ❌ エラー詳細ログ
- ❌ ユーザー認証機能
- ❌ CORS対応したGAS呼び出し（現在はno-corsモード）

## 🛠️ データアーキテクチャ

### データモデル

**OrderLine（発注行）:**
```typescript
{
  item: string;    // 品目名
  qty: number;     // 数量
  unit?: string;   // 単位
  note?: string;   // 備考
}
```

**OrderTotal（品目別合計）:**
```typescript
{
  item: string;    // 品目名
  qty: number;     // 合計数量
}
```

### ストレージサービス

- **LocalStorage**: GAS URL、アプリトークン設定
- **IndexedDB**: オフライン時の未送信データキュー
- **Service Worker Cache**: 静的リソース、CDNライブラリ

## 📖 使い方

### 1. アプリケーションのセットアップ

#### ローカル開発環境
```bash
# プロジェクトディレクトリへ移動
cd /home/user/webapp

# 依存関係のインストール（既にインストール済み）
npm install

# ビルド
npm run build

# PM2でサービス起動
pm2 start ecosystem.config.cjs

# サービス確認
curl http://localhost:3000
```

#### Google Apps Script の設定

1. **Googleスプレッドシートを作成**
   - 新しいスプレッドシートを作成
   - シート名を「明細」に変更（または自動作成されます）
   - （オプション）「A4_印刷」シートを作成してPDF出力用のレイアウトを設定

2. **Apps Scriptを開く**
   - `拡張機能` → `Apps Script` を開く

3. **以下のスクリプトをコピー＆ペースト:**

```javascript
function doPost(e) {
  const body = JSON.parse(e.postData.contents || '{}');
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName('明細') || ss.insertSheet('明細');
  
  // ヘッダー行の作成（初回のみ）
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(['ID','取込日時','発注日','品目','数量','単位','備考','画像名','OCR信頼度','ソース']);
  }
  
  // データの整形と追加
  const now = new Date();
  const orderDate = body.order_date ? new Date(body.order_date) : now;
  const rows = (body.lines || []).map(l => ([
    Utilities.getUuid(),                          // 一意のID
    now,                                          // 取込日時
    orderDate,                                    // 発注日
    (l.item||'').toString(),                      // 品目
    Number(l.qty||0),                             // 数量
    (l.unit||'').toString(),                      // 単位
    (l.note||'').toString(),                      // 備考
    (body.source?.image_name||'').toString(),     // 画像名
    Number(body.source?.confidence||0),           // OCR信頼度
    (body.source?.ocr_engine||'').toString()      // OCRソース
  ]));
  
  // 一括書き込み
  if (rows.length) {
    sheet.getRange(sheet.getLastRow()+1, 1, rows.length, rows[0].length).setValues(rows);
  }
  
  // A4印刷用PDFのURL生成
  const printSheet = ss.getSheetByName('A4_印刷');
  let pdfUrl = '';
  if (printSheet) {
    const exportUrl = ss.getUrl().replace(/edit$/, '') +
      'export?format=pdf&portrait=true&size=A4&sheetnames=false&printtitle=false&gridlines=false&fzr=false' +
      '&gid=' + printSheet.getSheetId();
    pdfUrl = exportUrl;
  }
  
  // レスポンス返却
  return ContentService.createTextOutput(JSON.stringify({
    ok: true,
    sheetUrl: ss.getUrl(),
    pdfUrl: pdfUrl
  })).setMimeType(ContentService.MimeType.JSON);
}
```

4. **デプロイ設定**
   - `デプロイ` → `新しいデプロイ` をクリック
   - 種類: `ウェブアプリ` を選択
   - 説明: 「発注スキャン集計API」など
   - 次のユーザーとして実行: `自分`
   - アクセスできるユーザー: `全員`（認証不要にする）
   - `デプロイ` をクリック

5. **デプロイURLをコピー**
   - 表示されるウェブアプリURL（`https://script.google.com/macros/s/.../exec`）をコピー
   - このURLをアプリの設定画面に貼り付けます

### スプレッドシートの構造

**「明細」シート:**
| ID | 取込日時 | 発注日 | 品目 | 数量 | 単位 | 備考 | 画像名 | OCR信頼度 | ソース |
|----|---------|-------|------|------|------|------|--------|-----------|--------|
| UUID | 2025-11-04... | 2025-11-03 | きゅうり | 12 | 袋 | | IMG_0001.jpg | 0.85 | tesseract |

**「A4_印刷」シート（オプション）:**
- このシートを作成すると、PDF出力用のフォーマットを自由にカスタマイズできます
- 例: ピボットテーブルで品目別集計を表示、ヘッダー/フッター追加など

### 2. アプリの使用方法

1. **設定を保存**
   - ブラウザで開発環境URLにアクセス
   - 画面下部の「設定」セクションで以下を入力:
     - Google Apps Script URL: `https://script.google.com/macros/s/.../exec`
     - アプリトークン: 任意の文字列（GAS側と一致させる）
   - 「設定を保存」をクリック

2. **発注書をスキャン**
   - 「画像を選択」または発注書をドラッグ&ドロップ
   - 「OCR処理を開始」をクリック
   - 処理完了まで待機（10-30秒）

3. **抽出結果を編集**
   - 誤認識された品目名・数量を修正
   - 必要に応じて行を追加/削除
   - 品目別合計を確認

4. **保存してPDF生成**
   - 「保存して印刷用PDFを生成」をクリック
   - スプレッドシートへのリンクとPDFリンクが表示される
   - iPhoneの場合: リンクを開き、共有→プリントでA4印刷

### 3. PWAインストール（スマホ）

**iPhone Safari:**
1. 開発環境URLにアクセス
2. 共有ボタン → 「ホーム画面に追加」
3. アプリ名を確認して「追加」

**Android Chrome:**
1. 開発環境URLにアクセス
2. メニュー → 「ホーム画面に追加」
3. 「インストール」をタップ

## 🚀 デプロイ

### Cloudflare Pagesへのデプロイ

```bash
# ビルド
npm run build

# Cloudflareへデプロイ（初回）
npx wrangler pages deploy dist --project-name order-scan

# 環境変数の設定（Google Cloud Vision API有効化時）
npx wrangler pages secret put GOOGLE_CLOUD_VISION_API_KEY --project-name order-scan
```

## 📁 プロジェクト構造

```
webapp/
├── src/
│   ├── index.tsx          # Hono バックエンド + /api/ocr
│   └── types.ts           # TypeScript型定義
├── public/
│   ├── app.js             # フロントエンドロジック（OCR、編集、保存）
│   ├── styles.css         # カスタムスタイル
│   ├── manifest.webmanifest  # PWA Manifest
│   ├── service-worker.js     # Service Worker（キャッシュ、オフライン対応）
│   └── icons/
│       ├── icon-192.png      # PWAアイコン（小）
│       └── icon-512.png      # PWAアイコン（大）
├── dist/                  # ビルド出力（自動生成）
├── logs/                  # PM2ログ
├── ecosystem.config.cjs   # PM2設定
├── package.json           # 依存関係とスクリプト
├── tsconfig.json          # TypeScript設定
├── vite.config.ts         # Vite設定
├── wrangler.jsonc         # Cloudflare設定
└── README.md              # このファイル
```

## 🔧 推奨される次のステップ

### 優先度: 高
1. **Google Apps Script スクリプトの作成**
   - スプレッドシートへのデータ書き込み実装
   - A4印刷用PDF生成機能の実装
   - CORS設定の確認

2. **実機テスト**
   - iPhone Safariでカメラ撮影→OCR→保存のフロー確認
   - PWAインストール確認
   - オフライン動作確認

3. **エラーハンドリング改善**
   - OCR失敗時の詳細エラー表示
   - GAS連携失敗時のリトライ機能
   - ネットワークエラー時の適切な通知

### 優先度: 中
4. **OCR精度向上**
   - 台形補正の実装
   - Google Cloud Vision API の有効化
   - 前処理パラメータの調整

5. **UI/UX改善**
   - 抽出結果の信頼度表示
   - 編集履歴の保存
   - ダークモード対応

6. **Cloudflare Pagesへのデプロイ**
   - 本番環境の構築
   - カスタムドメインの設定
   - 環境変数の設定

### 優先度: 低
7. **機能拡張**
   - 複数画像の一括処理
   - 履歴閲覧機能
   - CSVエクスポート機能
   - 品目マスタの管理

## 📝 ライセンス

MIT License

## 🙏 謝辞

- [Hono](https://hono.dev/) - 高速Webフレームワーク
- [Tesseract.js](https://tesseract.projectnaptha.com/) - JavaScript OCRエンジン
- [Tailwind CSS](https://tailwindcss.com/) - ユーティリティファーストCSSフレームワーク
- [Font Awesome](https://fontawesome.com/) - アイコンライブラリ
- [Cloudflare Pages](https://pages.cloudflare.com/) - エッジデプロイプラットフォーム

---

**最終更新日**: 2025-11-04  
**バージョン**: MVP 1.0.0  
**ステータス**: ✅ ローカル開発環境で動作確認済み
