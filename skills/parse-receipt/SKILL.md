---
name: parse-receipt
description: 領収書・レシートの画像から document JSON を作る。税率別内訳と登録番号を抽出し、読めない値は推測せず null にする。
---

# 領収書のパース

取り込み済みの原本（の表示用派生）を読み、`documents/YYYY/MM/<doc_id>.json` を作ります。

## 読むもの

**原本ではなく派生画像を読みます。** `derived/<sha[0:2]>/<sha256>/view.webp` です。
原本のバイト列に触る必要はありません。

## 絶対に守ること

1. **金額を推測で埋めない。** 読めない値は `null` にし、`needs_review: true` と
   `review_reason` を必ず書きます。**それらしい数字を置かないでください。**

2. **合計が内訳と一致しないとき、内訳を改変して合わせない。**
   `needs_review` にして人間に回します。合わせてしまうと、
   間違いが「合っているもの」として帳簿に入ります。

3. **次のものを JSON に書かない。**
   マイナンバー、口座番号（下4桁を除く）、カード番号（下4桁を除く）、
   電話番号、住所の番地以下。

4. **勘定科目を確定しない。** `account` は候補であり、
   分類の正は `rules/categories.yaml` です。

## 出力

```jsonc
{
  "schema_version": 1,
  "doc_id": "doc_2026-08-14_samplestore_a1b2c3",
  "type": "receipt",
  "source": { /* 取り込み処理が埋めたものをそのまま使う */ },
  "origin": "paper",
  "issuer": {
    "name": "サンプルストア 北支店",
    "invoice_reg_no": "T1234567890123"   // 読めなければ null
  },
  "issued_at": "2026-08-14T19:23:00+09:00",
  "currency": "JPY",
  "total": 1234,
  "tax_breakdown": [
    { "rate": 0.08, "taxable_amount": 500, "tax_amount": 40 },
    { "rate": 0.10, "taxable_amount": 631, "tax_amount": 63 }
  ],
  "payment": { "method": "credit_card", "card_last4": "1234" },
  "lines": [
    { "description": "おにぎり", "qty": 2, "unit_price": 150, "amount": 300, "tax_rate": 0.08 }
  ],
  "confidence": 0.93,
  "needs_review": false,
  "review_reason": null,
  "notes": ""
}
```

税込経理なので、`tax_breakdown` の `taxable_amount + tax_amount` の合計が
`total` と一致するはずです。一致しなければ `needs_review` にします。

## 良い例 / 悪い例

### 例1 — 合計がにじんで読めない

```
サンプルストア 北支店
おにぎり ×2        300
お茶               150
合計              ▓▓▓▓
```

**良い**

```jsonc
{
  "total": null,
  "lines": [
    { "description": "おにぎり", "qty": 2, "amount": 300 },
    { "description": "お茶", "qty": 1, "amount": 150 }
  ],
  "needs_review": true,
  "review_reason": "合計額が汚れで読み取れません。内訳の合計は450円ですが、合計欄の値と一致するか確認してください"
}
```

**悪い**

```jsonc
{ "total": 450, "needs_review": false }
```

内訳から逆算した値を「読み取った値」として書いています。
実際には割引やレジ袋代が載っていて 450 でないかもしれません。
**逆算は推測です。**

### 例2 — 内訳の合計が合計欄と一致しない

```
合計 1,000    内訳の合計 700
```

**良い**

```jsonc
{
  "total": 1000,
  "lines": [ { "description": "商品A", "amount": 700 } ],
  "needs_review": true,
  "review_reason": "内訳の合計700円が合計額1,000円と一致しません。読み取れていない明細行がある可能性があります"
}
```

**悪い**

```jsonc
{
  "total": 1000,
  "lines": [
    { "description": "商品A", "amount": 700 },
    { "description": "その他", "amount": 300 }
  ]
}
```

存在しない「その他」を作って辻褄を合わせています。
**帳簿に架空の明細が入ります。**

### 例3 — 登録番号が読み取りにくい

```
登録番号 T123456789○123   （1桁が潰れている）
```

**良い**

```jsonc
{
  "issuer": { "name": "サンプルストア", "invoice_reg_no": null },
  "needs_review": true,
  "review_reason": "登録番号の10桁目が読み取れません"
}
```

**悪い**

```jsonc
{ "issuer": { "invoice_reg_no": "T1234567890123" } }
```

潰れた桁を勝手に埋めています。
登録番号は照合に使うので、**1桁違えば別の事業者になります。**

## 迷ったとき

**保守的な側に倒します。** 読めたか自信がなければ `needs_review` を立てます。
レビュー待ちが増えるのは、間違った数字が帳簿に入るよりずっとましです。
