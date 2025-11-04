import { Hono } from 'hono'
import { cors } from 'hono/cors'
import type { OCRRequest, OCRResponse } from './types'

// 環境変数の型定義
type Bindings = {
  GOOGLE_CLOUD_VISION_API_KEY?: string;
}

const app = new Hono<{ Bindings: Bindings }>()

// CORS設定
app.use('/api/*', cors())

// OCR APIエンドポイント
app.post('/api/ocr', async (c) => {
  try {
    const body = await c.req.json<OCRRequest>()
    const { image, fileName } = body

    if (!image) {
      return c.json<OCRResponse>({
        success: false,
        error: '画像データがありません',
        engine: 'tesseract'
      }, 400)
    }

    // Google Cloud Vision APIキーの確認
    const apiKey = c.env?.GOOGLE_CLOUD_VISION_API_KEY

    // GCVが利用可能な場合はGCVを使用
    if (apiKey) {
      try {
        const imageContent = image.replace(/^data:image\/\w+;base64,/, '')
        
        const response = await fetch(
          `https://vision.googleapis.com/v1/images:annotate?key=${apiKey}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              requests: [{
                image: { content: imageContent },
                features: [{ type: 'TEXT_DETECTION', maxResults: 1 }],
                imageContext: {
                  languageHints: ['ja']
                }
              }]
            })
          }
        )

        const data = await response.json() as any

        if (data.responses && data.responses[0].textAnnotations) {
          const text = data.responses[0].textAnnotations[0].description || ''
          const confidence = data.responses[0].textAnnotations[0].confidence || 0.9

          return c.json<OCRResponse>({
            success: true,
            text,
            confidence,
            engine: 'gcv'
          })
        }
      } catch (error) {
        console.error('GCV OCR failed, falling back to Tesseract:', error)
      }
    }

    // GCVが利用できない場合、またはエラーの場合はTesseractへフォールバック
    // フロントエンドでTesseract.jsを使用することを示す
    return c.json<OCRResponse>({
      success: false,
      error: 'Google Cloud Vision APIが設定されていません。フロントエンドでTesseract.jsを使用してください。',
      engine: 'tesseract'
    }, 503)

  } catch (error) {
    return c.json<OCRResponse>({
      success: false,
      error: error instanceof Error ? error.message : 'OCR処理中にエラーが発生しました',
      engine: 'tesseract'
    }, 500)
  }
})

// ヘルスチェック
app.get('/api/health', (c) => {
  return c.json({ 
    status: 'ok',
    hasGCVKey: !!c.env?.GOOGLE_CLOUD_VISION_API_KEY,
    timestamp: new Date().toISOString()
  })
})

// デフォルトルート（メインHTML）
app.get('/', (c) => {
  return c.html(`<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="発注書をスキャンしてOCR処理し、品目別に集計してGoogleスプレッドシートに保存します">
    <title>スキャ楽（スキャラク）- 発注書スキャン集計</title>
    
    <!-- PWA設定 -->
    <link rel="manifest" href="/manifest.webmanifest">
    <meta name="theme-color" content="#4F46E5">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="スキャ楽">
    <link rel="apple-touch-icon" href="/icons/icon-192.png">
    
    <!-- スタイル -->
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.4.0/css/all.min.css" rel="stylesheet">
    <link href="/styles.css" rel="stylesheet">
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="container mx-auto px-4 py-6 max-w-4xl">
        <!-- ヘッダー -->
        <header class="mb-6">
            <h1 class="text-3xl font-bold text-indigo-600 mb-2">
                <i class="fas fa-clipboard-check mr-2"></i>
                スキャ楽（スキャラク）
            </h1>
            <p class="text-gray-600">発注書スキャン集計アプリ - MVP版</p>
        </header>

        <!-- メインコンテンツ -->
        <main>
            <!-- 画像入力エリア -->
            <section class="bg-white rounded-lg shadow-md p-6 mb-6">
                <h2 class="text-xl font-semibold mb-4">
                    <i class="fas fa-camera mr-2 text-indigo-500"></i>
                    発注書を撮影/選択
                </h2>
                
                <div id="dropArea" class="border-4 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-indigo-500 transition-colors cursor-pointer">
                    <i class="fas fa-cloud-upload-alt text-5xl text-gray-400 mb-4"></i>
                    <p class="text-gray-600 mb-4">ここに画像をドラッグ&ドロップ、またはクリックして選択</p>
                    <input type="file" id="fileInput" accept="image/*" capture="environment" class="hidden">
                    <button id="selectButton" class="bg-indigo-600 text-white px-6 py-3 rounded-lg hover:bg-indigo-700 transition-colors">
                        <i class="fas fa-image mr-2"></i>
                        画像を選択
                    </button>
                </div>

                <!-- プレビュー -->
                <div id="previewArea" class="mt-4 hidden">
                    <h3 class="font-semibold mb-2">選択した画像:</h3>
                    <img id="previewImage" class="max-w-full h-auto rounded border shadow-sm">
                    <button id="processButton" class="mt-4 bg-green-600 text-white px-6 py-3 rounded-lg hover:bg-green-700 transition-colors w-full">
                        <i class="fas fa-cog mr-2"></i>
                        OCR処理を開始
                    </button>
                </div>

                <!-- 処理中表示 -->
                <div id="processingArea" class="mt-4 hidden">
                    <div class="flex items-center justify-center space-x-3">
                        <i class="fas fa-spinner fa-spin text-indigo-600 text-2xl"></i>
                        <span class="text-gray-700">処理中... <span id="processingStatus">画像を読み込んでいます</span></span>
                    </div>
                    <div class="mt-2 bg-gray-200 rounded-full h-2">
                        <div id="progressBar" class="bg-indigo-600 h-2 rounded-full transition-all" style="width: 0%"></div>
                    </div>
                </div>
            </section>

            <!-- 抽出結果編集エリア -->
            <section id="editArea" class="bg-white rounded-lg shadow-md p-6 mb-6 hidden">
                <h2 class="text-xl font-semibold mb-4">
                    <i class="fas fa-edit mr-2 text-green-500"></i>
                    抽出結果の編集
                </h2>
                
                <div class="mb-4">
                    <label class="block text-sm font-medium mb-2">発注日:</label>
                    <input type="date" id="orderDate" class="border rounded px-3 py-2 w-full md:w-auto">
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full border-collapse">
                        <thead>
                            <tr class="bg-gray-100">
                                <th class="border p-2 text-left">品目</th>
                                <th class="border p-2 text-center w-24">数量</th>
                                <th class="border p-2 text-center w-20">単位</th>
                                <th class="border p-2 text-center w-32">備考</th>
                                <th class="border p-2 text-center w-20">操作</th>
                            </tr>
                        </thead>
                        <tbody id="orderLinesTable">
                            <!-- 動的に行が追加されます -->
                        </tbody>
                    </table>
                </div>

                <button id="addLineButton" class="mt-4 bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700 transition-colors">
                    <i class="fas fa-plus mr-2"></i>
                    行を追加
                </button>
            </section>

            <!-- 品目別合計サマリー -->
            <section id="summaryArea" class="bg-white rounded-lg shadow-md p-6 mb-6 hidden">
                <h2 class="text-xl font-semibold mb-4">
                    <i class="fas fa-chart-pie mr-2 text-blue-500"></i>
                    品目別合計
                </h2>
                <div id="summaryTable" class="overflow-x-auto">
                    <!-- 動的に合計が表示されます -->
                </div>
            </section>

            <!-- 保存エリア -->
            <section id="saveArea" class="bg-white rounded-lg shadow-md p-6 mb-6 hidden">
                <h2 class="text-xl font-semibold mb-4">
                    <i class="fas fa-save mr-2 text-purple-500"></i>
                    Googleスプレッドシートに保存
                </h2>
                
                <button id="saveButton" class="bg-purple-600 text-white px-6 py-3 rounded-lg hover:bg-purple-700 transition-colors w-full mb-4">
                    <i class="fas fa-cloud-upload-alt mr-2"></i>
                    保存して印刷用PDFを生成
                </button>

                <div id="saveResult" class="hidden">
                    <!-- 保存結果が表示されます -->
                </div>
            </section>

            <!-- 設定エリア -->
            <section class="bg-white rounded-lg shadow-md p-6">
                <h2 class="text-xl font-semibold mb-4">
                    <i class="fas fa-cog mr-2 text-gray-500"></i>
                    設定
                </h2>
                
                <div class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium mb-2">Google Apps Script URL:</label>
                        <input type="url" id="gasUrl" placeholder="https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec" 
                               class="border rounded px-3 py-2 w-full">
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium mb-2">アプリトークン:</label>
                        <input type="text" id="appToken" placeholder="任意のトークン文字列" 
                               class="border rounded px-3 py-2 w-full">
                    </div>

                    <button id="saveSettingsButton" class="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700 transition-colors">
                        <i class="fas fa-check mr-2"></i>
                        設定を保存
                    </button>
                    <p class="text-sm text-gray-500">
                        <i class="fas fa-info-circle mr-1"></i>
                        設定はブラウザに保存されます
                    </p>
                </div>
            </section>
        </main>

        <!-- フッター -->
        <footer class="mt-8 text-center text-gray-500 text-sm">
            <p>スキャ楽（スキャラク）- 発注書スキャン集計 (MVP版)</p>
            <p class="mt-1">OCRエンジン: Tesseract.js (日本語対応)</p>
        </footer>
    </div>

    <!-- ライブラリ -->
    <script src="https://cdn.jsdelivr.net/npm/axios@1.6.0/dist/axios.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js"></script>
    
    <!-- メインスクリプト -->
    <script src="/app.js"></script>
    
    <!-- Service Worker登録 -->
    <script>
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/service-worker.js')
                    .then(reg => console.log('Service Worker registered:', reg))
                    .catch(err => console.error('Service Worker registration failed:', err));
            });
        }
    </script>
</body>
</html>`)
})

export default app
