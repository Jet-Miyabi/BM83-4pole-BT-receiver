# 02 ブロック図（第1版、B1 直列中継構成）

最終更新: 2026-11-01。数値に「仮」と付いたものは、実測または資料確認の後に確定する。

```mermaid
flowchart LR
  subgraph Phone["Xperia 1 V (Android 15)"]
    APP["Claude app / MacroDroid"]
  end

  subgraph Headset["咽頭マイク（4極 CTIA、PTT 付き）"]
    MIC["咽頭マイク<br/>Sleeve=MIC"]
    PTT["PTT（MIC–GND を約1.25Ωで短絡）"]
    TUBE["エアチューブイヤホン<br/>Tip/Ring1"]
  end

  subgraph Board["自作基板"]
    J1["4極 3.5 mm ジャック"]
    BIAS["マイクバイアス<br/>低雑音LDO 2.5V（仮）→ RC → 2.2kΩ"]
    CMP["PTT 検出<br/>コンパレーター（オープンドレイン）<br/>しきい値 約0.4V（仮）"]
    BM1["BM83 #1（標準ファームウェア、Embedded）<br/>HFP/A2DP の受信機<br/>MICP1/MICN1、AOHPL/R（Single-End）"]
    SW["ディップスイッチ<br/>エアチューブ出力 ON/OFF"]
    BM2["BM83 #2（AT ファームウェア、Embedded）<br/>A2DP の送信機<br/>AIL/AIR（Aux-in）"]
    PWR["14500 Li-ion → 逆接続保護 P-MOSFET<br/>→ スライドスイッチ → BAT_IN ×2"]
    PROG["書き込み用ヘッダー ×2<br/>5V→ADAP_IN、P3_4、UART TX/RX、GND"]
  end

  OR["Shokz OpenRun (S803)"]

  MIC --- J1
  PTT --- J1
  J1 -->|"MIC（AC結合 0.047µF）"| BM1
  BIAS --> J1
  J1 -->|"DC電圧"| CMP
  CMP -->|"GPIO、アクティブロー<br/>短押し=AVRCP Play/Pause（仮）"| BM1
  BM1 <-->|"HFP（mSBC）+ AVRCP + A2DP"| Phone
  BM1 -->|"AOHPL/R → DCカット"| BM2
  BM1 -->|"AOHPL/R → DCカット"| SW --> J1 --> TUBE
  BM1 -.->|"外部アンプのイネーブル GPIO → Aux-in 検出（案、未確認）"| BM2
  BM2 -->|"A2DP（SBC）"| OR
  PWR --> BM1
  PWR --> BM2
  PWR --> BIAS
  PROG --- BM1
  PROG --- BM2
```

## 信号の流れ

1. **話す**: 咽頭マイク → BM83#1 の ADC → DSP（HPF/AEC/NR/送話EQ）→ mSBC → スマホ → Claude。
2. **応答を聞く**: Claude → スマホ → SCO（mSBC）→ BM83#1 の DAC → アナログのライン信号 → BM83#2 の Aux-in → SBC → OpenRun。
3. **PTT**: 押すと MIC 線が約 0 V になり、コンパレーターの出力が Low になる。BM83#1 がそれをボタン入力として受け、AVRCP の Play/Pause を送る。スマホ側の MacroDroid がそれを受けて Claude を起動する。

## 動作モードごとの消費電流（仮）

| 状態 | BM83#1 | BM83#2 | その他 | 合計 |
|---|---|---|---|---|
| 待機（接続済み） | Sniff 0.55 mA | Sniff 0.55 mA | バイアス 0.3 mA | 約 1.4 mA |
| 会話中 | SCO 約 16 mA | A2DP 送信 約 12 mA | — | 約 28 mA |

出典: [DS] p.61 Table 9-12。2 段目の行は、データシートの代表値に推定分（仮）を加えた値。
