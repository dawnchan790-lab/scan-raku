# ファミリーマート 納品書・請求書 作成システム

FAX・グループLINEで届いた注文を **仕分け帳** に振り分け、**納品書** を作成し、
**毎月20日締め** で **請求書** を作成します。

納品書・請求書は現行のExcel書式をテンプレートとして読み込み、
罫線・ロゴ・レイアウトを一切崩さずに値だけを流し込みます。

```
FAX（スキャン→OCR）┐
                    ├→ 仕分け帳（店舗×納品日）→ 納品書 →（20日締め）→ 請求書
グループLINE（本文） ┘
```

## セットアップ

```bash
cd familymart
pip install -r requirements.txt
```

### テンプレートの配置

`templates/` に現行の納品書・請求書のExcelを置きます。

```
templates/
├── 納品書.xlsx
└── 請求書.xlsx
```

現行ブックから切り出したものが既に入っています。作り直すときは:

```bash
python3 tools/build_templates.py
```

`templates/現行/` にある現行ブックを読み、帳票シート1枚だけを取り出して、
他シートを参照している数式を空欄化します（罫線・フォント・列幅・印刷設定はそのまま）。
**シート内で完結する数式（金額＝数量×単価、合計、消費税）は残してあるので、
計算は現行どおりExcelが行います。**

## 使い方

すべて `familymart/` ディレクトリで実行します。

```bash
export PYTHONPATH=src   # Windowsは  set PYTHONPATH=src
```

### 1. 注文を取り込む（仕分け）

LINEの本文をコピーしたテキスト、またはFAXをOCRしたテキストを渡します。

```bash
python3 -m fmbill torikomi 注文.txt --source line
python3 -m fmbill torikomi 注文.txt --source fax

# 保存せず読み取り結果だけ確認したいとき
python3 -m fmbill torikomi 注文.txt --dry-run

# 本文に店舗名や日付が書かれていないとき
python3 -m fmbill torikomi 注文.txt --store 0807230 --date 2026-08-07
```

1通のメッセージに複数店舗・複数納品日が混ざっていても自動で仕分けます。

```
ファミリーマート国見ヶ丘店     ← 店舗の見出し行
8/7 納品でお願いします          ← 納品日
きゅうり　3                    ← 明細（全角/半角、単位の有無はどちらでも可）
トマト 2パック
なす×5

国見ケ丘                       ← 略称でも認識します
8/10
きゅうり 2
```

商品マスタに無い品目は **捨てずに取り込み、`★要確認` として印を付けます**。
仕分け帳のその行は黄色で塗られます。

### 2. 仕分け帳を確認する

```bash
python3 -m fmbill shiwake --month 2026-08
# → output/仕分け帳_202608.xlsx
```

### 3. 納品書を作る

```bash
python3 -m fmbill nouhin --date 2026-08-07              # その日の全店舗ぶん
python3 -m fmbill nouhin --date 2026-08-07 --store 0807230
# → output/納品書_20260807_国見ヶ丘.xlsx
```

### 4. 請求書を作る（20日締め）

```bash
python3 -m fmbill seikyu --month 2026-08
python3 -m fmbill seikyu --month 2026-08 --issue-date 2026-08-22 --due 2026-08-31
# → output/請求書_202608_国見ケ丘.xlsx
```

`--month 2026-08` は **2026/07/21 〜 2026/08/20** が対象です。

## 店舗ごとの違いの設定

**コードは触りません。`config/` のファイルを編集するだけです。**

### config/stores.yaml — 店舗マスタ

```yaml
stores:
  - code: OOSATOYAMAZAKI
    name: ファミリーマート　大郷山崎店
    short_name: 大郷山崎
    group: 宗久グループ
    margin_rate: 0.10          # ← この店だけ掛け率10%
    aliases: [おおさとやまざき]  # LINE/FAXの表記ゆれ

  - code: TAKANOHARA
    name: ファミリーマート　仙台高野原店
    short_name: 仙台高野原
    group: マルカ系
    margin_rate: 0.28
    order_unit: lot            # ← ロット数で発注する
    delivery_fee:
      enabled: false           # ← この店だけ送料なし
```

`defaults:` に書いた内容が全店舗の既定値になり、店舗ごとの記述がそれを上書きします。

| 設定できること | キー |
|---|---|
| 掛け率（粗利益率） | `margin_rate` |
| 送料の有無 | `delivery_fee.enabled` |
| 送料の金額（税込） | `delivery_fee.amount` |
| 請求書の送料の品名 | `delivery_fee.label` |
| 発注の入れ方（数量／ロット数） | `order_unit`（`qty` / `lot`） |
| 商品の引き分け | `group` |
| 締め日 | `closing_day` |
| 請求書の宛名の敬称 | `honorific` |
| 納品書の宛名 | `note_name` |
| 表記ゆれからの店舗特定 | `aliases` |
| 店舗独自の商品呼称 | `item_aliases` |
| 使う帳票テンプレート | `delivery_note.template` / `invoice.template` |

### config/products.yaml — 商品マスタ（自動生成）

**このファイルは現行の発注書ブックから自動生成します。**手で書く必要はありません。

```bash
python3 tools/import_products.py \
  "templates/現行/⑥発注書納品書_宗久グループ_0807230.xlsx:宗久グループ" \
  "templates/現行/⑧発注書納品書_大町2丁目店_080801.xlsx:大町2丁目店（別オーナー）" \
  "templates/現行/③発注書納品書_マルカ系_7.21納品.xlsx:マルカ系"
```

売価が変わったら、最新の発注書ブックを渡して作り直してください。
そのブックで最も多い粗利益率をグループの既定とみなし、**そこから外れた品目だけ**
`margin_rate` を持たせます。ふだんは店舗の掛け率が効きます。

```yaml
products:
  - code: "宗久-トマト"
    name: "トマト"
    retail_price: 288         # 想定税込売価
    groups: ["宗久グループ"]   # 品目も売価もグループごとに違う
    shelf_life_days: 5
```

### config/aliases.yaml — 表記ゆれ辞書

商品マスタは再生成で上書きされるため、手で育てる表記ゆれはこちらに分けています。

```yaml
item_aliases:
  "宗久-胡瓜2本": [きゅうり, キュウリ, 胡瓜]
```

### config/layouts.yaml — 帳票のセル位置

現行のExcelのどのセルに何を書き込むかの対応表です。
テンプレートを差し替えたら、ここを実物のセル位置に合わせます。

```yaml
delivery_note:
  cells:
    store_name: B3            # 店舗名を書き込むセル
    delivery_date:
      ref: G2
      format: "%Y年%m月%d日"  # 省略すると日付型のまま（テンプレの表示形式に従う）
  rows:
    start: 7                  # 明細の開始行
    count: 18                 # 1ページに入る明細行数
    columns:
      no: A
      item_name: B
      qty: D
      unit: E
      unit_price: F
      amount: G
  overflow: new_sheet         # 明細が入り切らなければページを増やす
```

## 価格の計算

**金額はすべて税込で扱います。**現行のExcelがそうなっているためです。
単価マスタは持たず、想定税込売価と粗利益率（掛け率）から原価を毎回計算します。

```
原価（税込） = ROUNDUP( 想定税込売価 × ( 1 − 粗利益率 ), 0 )
```

| 店舗 | 粗利益率 | 送料 | 発注の入れ方 |
|---|---|---|---|
| 宗久グループ | 25% | あり | 数量 |
| 大郷山崎 | **10%** | あり | 数量 |
| 大町2丁目（別オーナー） | 25% | あり | 数量 |
| 仙台高野原 | 28% | **なし** | **ロット数** |
| 仙台上愛子・栗生4丁目 | 28% | あり | **ロット数** |

「ロット数」の店舗は、注文に書かれた数がロット数です。数量は `ロット数 × 最小発注ロット`。

## 消費税の扱い

- 食品は **軽減税率8%**、送料は **標準税率10%** で別々に集計します。
- 金額が税込なので、内消費税は税込金額から逆算します。
  8%は `税込 − 税込÷1.08`、10%は `税込 − 税込÷1.1`（＝税込÷11）。
- 送料550円は **納品1回ごと**。その日に1品でも納品があれば550円、なければ0円。
  現行の発注書の `=IF(SUM(店舗の列)<>0,550,0)` と同じ動きです。
- 「仏花」など食品でない品目は標準税率10%として取り込みます。

## データの保存場所

| 場所 | 内容 |
|---|---|
| `data/shiwake.db` | 仕分け帳の本体（SQLite）。**バックアップ対象** |
| `output/` | 生成した仕分け帳・納品書・請求書 |
| `templates/` | 現行書式のExcelテンプレート |

同じファイルを二度取り込んでも、店舗・納品日・取込元が同じなら重複登録しません。
取り込んだ元のテキストは1行ずつ `raw_text` として保存しているので、後から元の文面を確認できます。

## テスト

```bash
PYTHONPATH=src python3 -m pytest tests -q
```

## 構成

```
familymart/
├── config/
│   ├── stores.yaml       # 店舗マスタ（店舗ごとの違いはここで吸収）
│   ├── products.yaml     # 商品マスタ（発注書から自動生成）
│   ├── aliases.yaml      # 品目の表記ゆれ辞書（手で育てる）
│   └── layouts.yaml      # 帳票のセル位置
├── templates/            # 帳票テンプレート
│   └── 現行/             # 受領した現行ブックの原本
├── src/fmbill/
│   ├── textutil.py       # 全角/半角・和暦・数量の正規化
│   ├── parser.py         # FAX/LINEテキスト → 注文
│   ├── masters.py        # マスタ読み込みと表記ゆれ照合
│   ├── ledger.py         # 仕分け帳（SQLite）
│   ├── billing.py        # 締め期間・配送料・消費税の計算
│   ├── excel.py          # テンプレートへの流し込み
│   ├── import_orderbook.py  # 現行の発注書ブックの読み取り
│   ├── reports.py        # 仕分け帳のExcel出力
│   └── cli.py            # コマンド
├── tools/
│   ├── build_templates.py   # 現行ブック → 帳票テンプレート
│   └── import_products.py   # 現行の発注書 → 商品マスタ
├── docs/
│   └── 現行フォーマット分析.md
└── tests/
```

## 帳票の発行元

| 帳票 | 発行元 |
|---|---|
| 納品書 | 有限会社マルカ（仙台市太白区秋保湯元字寺田原45-11） |
| 請求書 | 株式会社 工藤祐作商店（仙台市若林区卸町四丁目3-1 / 登録番号 8370001002926） |

## これから決めること

- [ ] 実際のLINEの文面・FAXの注文票を見て、読み取りルールを合わせる
- [ ] `config/aliases.yaml` に表記ゆれを登録する
- [ ] 請求書番号（`発行番号`）の採番ルール
- [ ] 納品書の必要部数・控えの要否
- [ ] 請求書の明細が26行を超える場合の扱い（現在はエラーで止まります）
- [ ] FAXのOCR経路を既存の「スキャ楽」とつなぐ（現在はテキストを渡す前提）

> **仕分け表への反映は未実装です。**（ご指示により保留中）
