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

> **現在は暫定テンプレートが入っています。**
> 現行の `0807230.xlsx` などを受け取り次第、実物に差し替えて
> `config/layouts.yaml` のセル位置を実物に合わせます。
> 暫定テンプレートは `python3 tools/make_placeholder_templates.py` で再生成できます。

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
# → output/請求書_202608_国見ヶ丘.xlsx
```

`--month 2026-08` は **2026/07/21 〜 2026/08/20** が対象です。

## 店舗ごとの違いの設定

**コードは触りません。`config/` のファイルを編集するだけです。**

### config/stores.yaml — 店舗マスタ

```yaml
stores:
  - code: "0807230"
    name: ファミリーマート国見ヶ丘店
    short_name: 国見ヶ丘
    aliases: [国見ケ丘, 国見が丘]   # LINE/FAXの表記ゆれ
    delivery_fee:
      enabled: true                 # ← 配送料550円（税込）をもらう店
    item_aliases:
      パセリ: イタリアンパセリ        # この店だけの呼び方 → 自社の正式品目名

  - code: "SAMPLE-02"
    name: ファミリーマート（サンプル）2号店
    delivery_fee:
      enabled: false                # ← 配送料をもらわない店
```

`defaults:` に書いた内容が全店舗の既定値になり、店舗ごとの記述がそれを上書きします。

| 設定できること | キー |
|---|---|
| 配送料の有無 | `delivery_fee.enabled` |
| 配送料の金額（税込） | `delivery_fee.amount` |
| 配送料を月1回かける／納品ごとにかける | `delivery_fee.charge_unit`（`per_month` / `per_delivery`） |
| 締め日 | `closing_day` |
| 宛名の敬称 | `honorific` |
| 表記ゆれからの店舗特定 | `aliases` |
| 店舗独自の商品呼称 | `item_aliases` |
| 使う帳票テンプレート | `delivery_note.template` / `invoice.template` |

### config/products.yaml — 商品マスタ

```yaml
products:
  - code: P002
    name: トマト
    unit: パック
    price: 220                # 標準単価（税抜）
    tax_rate: 8               # 食品は8%、それ以外は10%
    aliases: [とまと, ﾄﾏﾄ]
    store_prices:
      "0807230": 230          # この店だけ単価が違う場合
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

## 消費税の扱い

- 食品は **軽減税率8%**、配送料は **標準税率10%** で別々に集計します。
- 消費税額は **税率ごとに1回だけ** 端数処理（円未満切り捨て）します。
  行ごとに端数処理しないため、区分記載請求書の要件に合います。
- 配送料550円は **税込金額** として設定し、税抜500円＋消費税50円に分解します。

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
│   ├── products.yaml     # 商品マスタ
│   └── layouts.yaml      # 帳票のセル位置
├── templates/            # 現行書式のExcel
├── src/fmbill/
│   ├── textutil.py       # 全角/半角・和暦・数量の正規化
│   ├── parser.py         # FAX/LINEテキスト → 注文
│   ├── masters.py        # マスタ読み込みと表記ゆれ照合
│   ├── ledger.py         # 仕分け帳（SQLite）
│   ├── billing.py        # 締め期間・配送料・消費税の計算
│   ├── excel.py          # テンプレートへの流し込み
│   ├── reports.py        # 仕分け帳のExcel出力
│   └── cli.py            # コマンド
├── tools/                # 暫定テンプレート生成
└── tests/
```

## これから決めること

- [ ] 現行の納品書・請求書Excelを `templates/` に配置し、`layouts.yaml` を実物に合わせる
- [ ] 実際の店舗一覧・商品一覧・単価をマスタに登録する
- [ ] FAXのOCR経路を既存の「スキャ楽」とつなぐ（現在はテキストを渡す前提）
- [ ] 請求書番号の採番ルール
- [ ] 納品書の控えの要否・必要部数
