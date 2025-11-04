// 発注書データ型定義

export interface OrderLine {
  item: string;        // 品目名
  qty: number;         // 数量
  unit?: string;       // 単位（個、本、袋など）
  note?: string;       // 備考
}

export interface OrderTotal {
  item: string;        // 品目名
  qty: number;         // 合計数量
}

export interface SourceInfo {
  image_name: string;  // 画像ファイル名
  ocr_engine: 'gcv' | 'tesseract';  // 使用したOCRエンジン
  confidence?: number; // 信頼度
}

export interface OrderData {
  order_date: string;       // YYYY-MM-DD形式
  lines: OrderLine[];       // 抽出された行データ
  totals: OrderTotal[];     // 品目別合計
  source: SourceInfo;       // ソース情報
}

export interface GASResponse {
  success: boolean;
  sheetUrl?: string;        // Googleスプレッドシートへのリンク
  pdfUrl?: string;          // A4印刷PDFへのリンク
  message?: string;
  error?: string;
}

export interface OCRRequest {
  image: string;            // Base64エンコードされた画像データ
  fileName?: string;        // ファイル名
}

export interface OCRResponse {
  success: boolean;
  text?: string;            // 抽出されたテキスト
  confidence?: number;      // 信頼度
  engine: 'gcv' | 'tesseract';
  error?: string;
}
