#!/usr/bin/env python3
"""Generate the KiCad 7 schematic, BOM and BM83 footprint for dev board v0.

Single source of truth for the v0 design: edit PARTS below and re-run.

    python3 hardware/tools/gen_v0.py

Outputs (relative to repo root):
    hardware/bm83_rx_v0/bm83_rx_v0.kicad_sch
    hardware/bm83_rx_v0/bm83_rx_v0.kicad_pro
    hardware/bm83_rx_v0/fp-lib-table
    hardware/bm83_rx_v0/bom_v0.csv
    hardware/lib/BM83.pretty/BM83SM1.kicad_mod
"""
import copy
import csv
import json
import os
import uuid as uuidlib

from sexpr import Sym, dump, find, parse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "hardware", "bm83_rx_v0")
LIBOUT = os.path.join(ROOT, "hardware", "lib", "BM83.pretty")
KISYM = "/usr/share/kicad/symbols"
PROJECT = "bm83_rx_v0"

_ns = uuidlib.UUID("6f1d3c2e-8b1a-4e57-9a51-0000b83a0001")


def uid(*key):
    return str(uuidlib.uuid5(_ns, "/".join(str(k) for k in key)))


ROOT_UUID = uid("root")

# --------------------------------------------------------------------------
# Library symbols
# --------------------------------------------------------------------------
_libcache = {}


def _load_lib(lib):
    if lib not in _libcache:
        with open(os.path.join(KISYM, lib + ".kicad_sym"), encoding="utf-8") as f:
            tree = parse(f.read())
        _libcache[lib] = {n[1]: n for n in find(tree, "symbol")}
    return _libcache[lib]


def _rename_units(node, old, new):
    for sub in find(node, "symbol"):
        if sub[1].startswith(old + "_"):
            sub[1] = new + sub[1][len(old):]


def lib_symbol(lib_id):
    lib, name = lib_id.split(":")
    syms = _load_lib(lib)
    node = copy.deepcopy(syms[name])
    ext = find(node, "extends")
    if ext:
        parent = copy.deepcopy(syms[ext[0][1]])
        _rename_units(parent, parent[1], name)
        props = find(node, "property")
        body = [x for x in parent[2:] if not (isinstance(x, list) and x and x[0] == "property")]
        node = [Sym("symbol"), name] + props + body
    node[1] = lib_id
    pins = {}
    for sub in find(node, "symbol"):
        for p in find(sub, "pin"):
            at = find(p, "at")[0]
            num = find(p, "number")[0][1]
            hidden = "hide" in [x for x in p if not isinstance(x, list)]
            pins[num] = dict(x=float(at[1]), y=float(at[2]), a=int(float(at[3])),
                             type=str(p[1]), hidden=hidden)
    return node, pins


# --------------------------------------------------------------------------
# Custom BM83 symbol
# --------------------------------------------------------------------------
BM83_LEFT = [
    ("23", "BAT_IN", "power_in"), ("22", "ADAP_IN", "power_in"), ("24", "SYS_PWR", "power_out"),
    ("25", "VDD_IO", "power_out"), ("26", "PWR(MFB)", "input"), ("43", "RST_N", "input"),
    ("14", "MICP1", "input"), ("13", "MICN1", "input"), ("15", "MICBIAS", "power_out"),
    ("10", "MICP2", "input"), ("9", "MICN2", "input"), ("12", "AIL", "input"), ("11", "AIR", "input"),
    ("8", "AOHPL", "output"), ("6", "AOHPR", "output"), ("7", "AOHPM", "output"),
    ("17", "DMIC_CLK", "output"), ("19", "DMIC1_L", "input"), ("18", "DMIC1_R", "input"),
    ("27", "SK1_AMB_DET", "input"), ("28", "SK2_KEY_AD", "input"), ("37", "DP", "bidirectional"),
    ("36", "DM", "bidirectional"), ("32", "LED1", "open_collector"), ("34", "LED2", "open_collector"),
    ("16", "GND", "power_in"), ("50", "GND", "power_in"), ("56", "GND(PAD)", "power_in"),
    ("57", "GND(PAD)", "power_in"),
]
BM83_RIGHT = [
    ("30", "P8_5/UART_TXD", "bidirectional"), ("29", "P8_6/UART_RXD", "bidirectional"),
    ("31", "P3_4/UART_RTS/SYS_CFG", "bidirectional"), ("48", "P3_7/UART_CTS", "bidirectional"),
    ("49", "P0_0/UART_TX_IND", "bidirectional"), ("44", "P0_1", "bidirectional"),
    ("33", "P0_2", "bidirectional"), ("38", "P0_3", "bidirectional"), ("40", "P0_5", "bidirectional"),
    ("35", "P0_6", "bidirectional"), ("45", "P0_7", "bidirectional"),
    ("46", "P1_2/TDI_CPU/SCL", "bidirectional"), ("47", "P1_3/TCK_CPU/SDA", "bidirectional"),
    ("41", "P1_6/PWM1", "bidirectional"), ("42", "P2_3", "bidirectional"), ("21", "P2_6", "bidirectional"),
    ("39", "P2_7", "bidirectional"), ("20", "P3_2", "bidirectional"),
    ("1", "DR1", "input"), ("2", "RFS1", "bidirectional"), ("3", "SCLK1", "bidirectional"),
    ("4", "DT1", "output"), ("5", "MCLK1", "output"),
]
assert sorted(int(p[0]) for p in BM83_LEFT + BM83_RIGHT) == list(range(1, 51)) + [56, 57]


def bm83_symbol():
    name = "BM83_Project:BM83SM1"
    pitch = 2.54
    n = max(len(BM83_LEFT), len(BM83_RIGHT))
    top = (n - 1) * pitch / 2
    top = round(top / 1.27) * 1.27
    w = 17.78
    pins = {}
    pin_nodes = []

    def add(side, idx, num, pname, ptype):
        y = round(top - idx * pitch, 2)
        x = -w - 2.54 if side == "L" else w + 2.54
        a = 0 if side == "L" else 180
        pins[num] = dict(x=x, y=y, a=a, type=ptype, hidden=False)
        pin_nodes.append([Sym("pin"), Sym(ptype), Sym("line"), [Sym("at"), x, y, a],
                          [Sym("length"), 2.54],
                          [Sym("name"), pname, [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]]]],
                          [Sym("number"), num, [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]]]]])

    for i, (num, pn, pt) in enumerate(BM83_LEFT):
        add("L", i, num, pn, pt)
    for i, (num, pn, pt) in enumerate(BM83_RIGHT):
        add("R", i, num, pn, pt)
    bot = top - (n - 1) * pitch
    eff = [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]]]
    effh = [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], Sym("hide")]
    node = [Sym("symbol"), name, [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
            [Sym("property"), "Reference", "U", [Sym("at"), 0, top + 3.81, 0], eff],
            [Sym("property"), "Value", "BM83SM1", [Sym("at"), 0, bot - 3.81, 0], eff],
            [Sym("property"), "Footprint", "BM83:BM83SM1", [Sym("at"), 0, 0, 0], effh],
            [Sym("property"), "Datasheet", "DS70005402H", [Sym("at"), 0, 0, 0], effh],
            [Sym("symbol"), "BM83SM1_0_1",
             [Sym("rectangle"), [Sym("start"), -w, top + 2.54], [Sym("end"), w, bot - 2.54],
              [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]],
              [Sym("fill"), [Sym("type"), Sym("background")]]]],
            [Sym("symbol"), "BM83SM1_1_1"] + pin_nodes]
    return node, pins


# --------------------------------------------------------------------------
# Design data
# --------------------------------------------------------------------------
G = 2.54  # grid


def g(v):
    return round(v / G) * G


FP_R = "Resistor_SMD:R_0603_1608Metric"
FP_C = "Capacitor_SMD:C_0603_1608Metric"
FP_C08 = "Capacitor_SMD:C_0805_2012Metric"
FP_C12 = "Capacitor_SMD:C_1206_3216Metric"
FP_LED = "LED_SMD:LED_0603_1608Metric"
FP_TVS = "Diode_SMD:D_SOD-323"
FP_SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
FP_SOT23 = "Package_TO_SOT_SMD:SOT-23"
FP_SW = "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2"
FP_H6 = "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical"
FP_H16 = "Connector_PinHeader_2.54mm:PinHeader_2x08_P2.54mm_Vertical"
FP_SJ3 = "Jumper:SolderJumper-3_P1.3mm_Open_Pad1.0x1.5mm"

PARTS = []


def P(ref, lib_id, value, fp, x, y, nets, dnp=False, mpn="", note=""):
    PARTS.append(dict(ref=ref, lib_id=lib_id, value=value, fp=fp, x=g(x), y=g(y), nets=nets,
                      dnp=dnp, mpn=mpn, note=note))


def R(ref, val, x, y, n1, n2, **kw):
    P(ref, "Device:R", val, FP_R, x, y, {"1": n1, "2": n2}, **kw)


def C(ref, val, x, y, n1, n2, fp=FP_C, **kw):
    P(ref, "Device:C", val, fp, x, y, {"1": n1, "2": n2}, **kw)


TEXTS = []


def T(x, y, text, size=1.8):
    TEXTS.append((g(x), g(y), text, size))


# ---- Power ----------------------------------------------------------------
T(25, 25, "POWER: 14500 Li-ion (4.2V max only) -> reverse-polarity P-FET -> slide switch -> VBAT", 2.2)
P("BT1", "Device:Battery_Cell", "14500 Li-ion", "Battery:BatteryHolder_Keystone_2460_1xAA",
  35, 55, {"1": "BAT_RAW", "2": "GND"},
  mpn="Keystone 2460 (要: 保護付きセルの長さ適合確認)", note="4.35V高電圧セル/LiFePO4不可")
P("Q1", "Device:Q_PMOS_GSD", "AO3401A", FP_SOT23, 60, 50,
  {"1": "Q1_G", "2": "VBAT_P", "3": "BAT_RAW"}, mpn="AO3401A", note="逆接続保護: D=電池側, S=負荷側")
R("R1", "100k", 50, 70, "Q1_G", "GND")
P("SW1", "Switch:SW_SPDT", "POWER", "Button_Switch_SMD:SW_SPDT_PCM12", 90, 50,
  {"2": "VBAT_P", "1": "VBAT"}, mpn="C&K PCM12SMTR")
C("C1", "10u", 115, 55, "VBAT", "GND", fp=FP_C08, note="U1 BAT_IN直近")
C("C2", "10u", 127, 55, "VBAT", "GND", fp=FP_C08, note="U2 BAT_IN直近")
C("C3", "100n", 139, 55, "VBAT", "GND")

# ---- Mic bias LDO -------------------------------------------------------------
T(25, 95, "MIC BIAS (always-on, independent of MICBIAS so PTT works in idle)", 2.2)
P("U3", "Regulator_Linear:TLV75525PDBV", "TLV75525PDBV", FP_SOT235, 55, 115,
  {"1": "VBAT", "3": "VBAT", "2": "GND", "5": "V2V5"}, mpn="TI TLV75525PDBVR",
  note="2.5V LDO, Iq≈25µA. 雑音はR2/C5で減衰")
C("C4", "1u", 35, 118, "VBAT", "GND")
C("C15", "1u", 75, 118, "V2V5", "GND")
R("R2", "1k", 90, 115, "V2V5", "BIAS_F")
C("C5", "10u", 102, 118, "BIAS_F", "GND", fp=FP_C08, note="R2とでfc≈16Hz")
P("JP1", "Jumper:SolderJumper_3_Open", "BIAS_SEL", FP_SJ3, 125, 112,
  {"1": "BIAS_F", "2": "BIAS_SEL", "3": "MICBIAS1"}, note="既定 1-2短絡(自前バイアス)。2-3でBM83 MICBIAS")
R("R3", "2.2k", 150, 115, "BIAS_SEL", "MIC", note="Microchip ref R6=2.2k")
C("C6", "1u", 165, 118, "MICBIAS1", "GND", note="Microchip ref C22")

# ---- Jack & mic input --------------------------------------------------------
T(25, 140, "4-POLE CTIA JACK: T/R1=air-tube earpiece, R2=mic return, S=MIC", 2.2)
P("J1", "Connector_Audio:AudioJack4", "TRRS CTIA", "Connector_Audio:Jack_3.5mm_KoreanHropartsElec_PJ-320D-4A_Horizontal",
  35, 160, {"T": "HP_T", "R1": "HP_R", "R2": "MIC_RET", "S": "MIC"}, mpn="Korean Hroparts PJ-320D-4A (LCSC C95562)")
R("R4", "0", 60, 165, "MIC_RET", "GND", note="ジャック直近の1点でGNDへ(ネットタイ)")
C("C9", "220p", 75, 165, "MIC", "MIC_RET", note="Microchip ref C27")
C("C7", "47n", 90, 165, "MIC", "MICP1", note="DCカット。100nと比較(V4)")
C("C8", "47n", 105, 165, "MIC_RET", "MICN1", note="DCカット。100nと比較(V4)")

# ---- PTT detect -----------------------------------------------------------------
T(130, 148, "PTT DETECT: PTT shorts MIC-GND (1.25 ohm meas.) -> PTT_N low -> U1 P0_2 (PLAY/PAUSE)", 2.2)
R("R5", "100k", 135, 160, "MIC", "PTT_F")
C("C10", "100n", 147, 168, "PTT_F", "GND", note="τ=10ms 音声成分除去")
R("R6", "2.2M", 160, 160, "V2V5", "PTT_TH")
R("R7", "390k", 160, 182, "PTT_TH", "GND", note="Vth≈0.38V")
P("U4", "Comparator:TLV7041DBV", "TLV7041DBV", FP_SOT235, 190, 168,
  {"3": "PTT_F", "4": "PTT_TH", "1": "PTT_N", "5": "V2V5", "2": "GND"}, mpn="TI TLV7041DBVR",
  note="ナノパワー, オープンドレイン出力")
C("C11", "100n", 210, 170, "V2V5", "GND")
R("R8", "10M", 225, 165, "PTT_N", "PTT_F", dnp=True, note="ヒステリシス用(DNP)")
P("SW2", "Switch:SW_Push", "PLAY(test)", FP_SW, 240, 185, {"1": "PTT_N", "2": "GND"}, note="PTTと並列の試験用ボタン")
P("D1", "Device:D_TVS", "PESD5V0S1BA", FP_TVS, 240, 200, {"1": "PTT_N", "2": "GND"}, mpn="Nexperia PESD5V0S1BA")
C("C12", "15p", 255, 200, "PTT_N", "GND", note="Microchip ref ボタン入力")

# ---- U1 BM83 #1 (sink / throat mic) ------------------------------------------------
T(300, 25, "U1: BM83 #1  standard firmware (Embedded) - HFP/A2DP sink, throat mic", 2.2)
U1 = {"23": "VBAT", "22": "ADAP1", "24": "SYSPWR1", "26": "MFB1", "43": "RST1",
      "14": "MICP1", "13": "MICN1", "15": "MICBIAS1", "8": "HPL1", "6": "HPR1",
      "32": "LED1A", "34": "LED1B", "16": "GND", "50": "GND", "56": "GND", "57": "GND",
      "30": "TX1", "29": "RX1", "31": "CFG1", "33": "PTT_N",
      "48": "U1_P3_7", "49": "U1_P0_0", "44": "U1_P0_1", "38": "U1_P0_3", "40": "U1_P0_5",
      "35": "U1_P0_6", "45": "U1_P0_7", "46": "U1_P1_2", "47": "U1_P1_3", "41": "U1_P1_6",
      "42": "LINK_EN", "21": "U1_P2_6", "39": "U1_P2_7", "20": "U1_P3_2",
      "1": "U1_DR1", "2": "U1_RFS1", "3": "U1_SCLK1", "4": "U1_DT1", "5": "U1_MCLK1"}
P("U1", "BM83_Project:BM83SM1", "BM83SM1-00AA", "BM83:BM83SM1", 340, 80, U1,
  mpn="Microchip BM83SM1-00AA / -00AB", note="AOHPM未接続(Single-End)")
C("C13", "10u", 300, 140, "ADAP1", "GND", fp=FP_C08, note="Microchip ref C31")
P("SW3", "Switch:SW_Push", "MFB1", FP_SW, 300, 160, {"1": "SYSPWR1", "2": "MFB1"}, note="MFBはSYS_PWRへ引上げ(アクティブハイ)")
P("D2", "Device:D_TVS", "PESD5V0S1BA", FP_TVS, 300, 175, {"1": "MFB1", "2": "GND"}, mpn="Nexperia PESD5V0S1BA")
C("C14", "15p", 315, 175, "MFB1", "GND")
P("D3", "Device:LED", "RED", FP_LED, 340, 160, {"2": "SYSPWR1", "1": "LED1A"}, note="LEDドライバ直結(電流はConfigで設定)")
P("D4", "Device:LED", "BLUE", FP_LED, 340, 172, {"2": "SYSPWR1", "1": "LED1B"})
P("J2", "Connector_Generic:Conn_01x06", "PROG1", FP_H6, 380, 165,
  {"1": "CFG1", "2": "GND", "3": "TX1", "4": "RX1", "5": "ADAP1", "6": "RST1"},
  note="1-2ジャンパ=Test mode。書込時は電池OFFでADAP_INに5V")
P("J4", "Connector_Generic:Conn_02x08_Odd_Even", "GPIO1", FP_H16, 300, 205,
  {"1": "U1_P0_0", "2": "U1_P0_1", "3": "U1_P0_3", "4": "U1_P0_5", "5": "U1_P0_6", "6": "U1_P0_7",
   "7": "U1_P1_2", "8": "U1_P1_3", "9": "U1_P1_6", "10": "LINK_EN", "11": "U1_P2_6", "12": "U1_P2_7",
   "13": "U1_P3_2", "14": "U1_P3_7", "15": "GND", "16": "GND"})
P("J5", "Connector_Generic:Conn_01x06", "I2S1", FP_H6, 365, 205,
  {"1": "U1_DR1", "2": "U1_RFS1", "3": "U1_SCLK1", "4": "U1_DT1", "5": "U1_MCLK1", "6": "GND"},
  note="I2S連携の実験用")

# ---- Audio out of U1 -------------------------------------------------------------
T(25, 230, "U1 AUDIO OUT (Config: Speaker Output = Single End): line to U2 Aux-in + optional air-tube earpiece", 2.2)
for i, (ch, src, dst) in enumerate([("L", "HPL1", "AIL2"), ("R", "HPR1", "AIR2")]):
    y0 = 250 + i * 35
    C(f"C{20 + i * 3}", "4.7u", 35, y0, src, f"LINE{ch}_A", fp=FP_C08)
    R(f"R{10 + i * 3}", "10k", 50, y0 + 3, f"LINE{ch}_A", "GND")
    R(f"R{11 + i * 3}", "1k", 65, y0, f"LINE{ch}_A", f"LINE{ch}_B")
    C(f"C{21 + i * 3}", "470p", 80, y0 + 3, f"LINE{ch}_B", "GND", note="Microchip ref Aux入力")
    C(f"C{22 + i * 3}", "10u", 95, y0, f"LINE{ch}_B", dst, fp=FP_C08, note="Microchip ref C5/C7")
C("C26", "100u", 140, 255, "HPL1", "HPL_J", fp=FP_C12, note="DCカット 32Ωでfc≈50Hz")
C("C27", "100u", 155, 255, "HPR1", "HPR_J", fp=FP_C12)
P("SW4", "Switch:SW_DIP_x02", "EARPIECE", "Button_Switch_SMD:SW_DIP_SPSTx02_Slide_6.7x6.64mm_W8.61mm_P2.54mm_LowProfile",
  190, 260, {"1": "HPL_J", "4": "HP_T", "2": "HPR_J", "3": "HP_R"}, note="ON=エアチューブイヤホンへ出力")
R("R16", "10k", 215, 265, "HP_T", "GND", note="ポップ低減ブリーダ")
R("R17", "10k", 228, 265, "HP_R", "GND")

# ---- U2 BM83 #2 (AT firmware, A2DP source to OpenRun) ---------------------------------
T(450, 25, "U2: BM83 #2  AT firmware (Embedded) - A2DP source to Shokz OpenRun", 2.2)
U2 = {"23": "VBAT", "22": "ADAP2", "24": "SYSPWR2", "26": "MFB2", "43": "RST2",
      "12": "AIL2", "11": "AIR2", "32": "LED2A", "34": "LED2B",
      "16": "GND", "50": "GND", "56": "GND", "57": "GND",
      "30": "TX2", "29": "RX2", "31": "CFG2", "20": "AUXDET2",
      "48": "U2_P3_7", "49": "U2_P0_0", "44": "U2_P0_1", "33": "U2_P0_2", "38": "U2_P0_3",
      "40": "U2_P0_5", "35": "U2_P0_6", "45": "U2_P0_7", "46": "U2_P1_2", "47": "U2_P1_3",
      "41": "U2_P1_6", "42": "U2_P2_3", "21": "U2_P2_6", "39": "U2_P2_7",
      "1": "U2_DR1", "2": "U2_RFS1", "3": "U2_SCLK1", "4": "U2_DT1", "5": "U2_MCLK1"}
P("U2", "BM83_Project:BM83SM1", "BM83SM1-00TA", "BM83:BM83SM1", 500, 80, U2,
  mpn="Microchip BM83SM1-00TA (AT FW書込済の情報あり, 要確認)")
C("C30", "10u", 460, 140, "ADAP2", "GND", fp=FP_C08)
P("SW5", "Switch:SW_Push", "MFB2", FP_SW, 460, 160, {"1": "SYSPWR2", "2": "MFB2"}, note="長押しでOpenRun探索")
P("D5", "Device:D_TVS", "PESD5V0S1BA", FP_TVS, 460, 175, {"1": "MFB2", "2": "GND"}, mpn="Nexperia PESD5V0S1BA")
C("C31", "15p", 475, 175, "MFB2", "GND")
P("D6", "Device:LED", "RED", FP_LED, 500, 160, {"2": "SYSPWR2", "1": "LED2A"})
P("D7", "Device:LED", "BLUE", FP_LED, 500, 172, {"2": "SYSPWR2", "1": "LED2B"})
P("J3", "Connector_Generic:Conn_01x06", "PROG2", FP_H6, 540, 165,
  {"1": "CFG2", "2": "GND", "3": "TX2", "4": "RX2", "5": "ADAP2", "6": "RST2"})
P("J6", "Connector_Generic:Conn_02x08_Odd_Even", "GPIO2", FP_H16, 460, 205,
  {"1": "U2_P0_0", "2": "U2_P0_1", "3": "U2_P0_2", "4": "U2_P0_3", "5": "U2_P0_5", "6": "U2_P0_6",
   "7": "U2_P0_7", "8": "U2_P1_2", "9": "U2_P1_3", "10": "U2_P1_6", "11": "U2_P2_3", "12": "U2_P2_6",
   "13": "U2_P2_7", "14": "U2_P3_7", "15": "GND", "16": "GND"},
  note="AT FWの送信/受信・入力切替GPIOをここでGNDへ")
P("J7", "Connector_Generic:Conn_01x06", "I2S2", FP_H6, 525, 205,
  {"1": "U2_DR1", "2": "U2_RFS1", "3": "U2_SCLK1", "4": "U2_DT1", "5": "U2_MCLK1", "6": "GND"})
P("JP2", "Jumper:SolderJumper_3_Open", "AUXDET_SEL", FP_SJ3, 470, 245,
  {"1": "GND", "2": "AUXDET2", "3": "LINK_EN_R"}, note="1-2: Aux常時検出 / 2-3: U1 GPIO連動(D11案)")
R("R18", "1k", 495, 245, "LINK_EN_R", "LINK_EN")

# --------------------------------------------------------------------------
# Emit schematic
# --------------------------------------------------------------------------


def eff(size=1.27, hide=False, justify=None):
    e = [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]
    if justify:
        e.append([Sym("justify")] + [Sym(j) for j in justify.split()])
    if hide:
        e.append(Sym("hide"))
    return e


LABEL_ANGLE = {0: 180, 180: 0, 90: 270, 270: 90}
LABEL_JUST = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}


def build():
    libs, pinmaps = {}, {}
    for p in PARTS:
        if p["lib_id"] not in libs:
            if p["lib_id"].startswith("BM83_Project:"):
                libs[p["lib_id"]], pinmaps[p["lib_id"]] = bm83_symbol()
            else:
                libs[p["lib_id"]], pinmaps[p["lib_id"]] = lib_symbol(p["lib_id"])

    sch = [Sym("kicad_sch"), [Sym("version"), Sym("20230121")], [Sym("generator"), Sym("eeschema")],
           [Sym("uuid"), ROOT_UUID], [Sym("paper"), "A2"],
           [Sym("title_block"), [Sym("title"), "BM83 throat-mic BT receiver - dev board v0"],
            [Sym("date"), "2026-11-01"], [Sym("rev"), "v0.1"],
            [Sym("comment"), 1, "Generated by hardware/tools/gen_v0.py - edit the script, not this file"],
            [Sym("comment"), 2, "Values marked 仮/要確認 in BOM must be verified before ordering"]],
           [Sym("lib_symbols")] + list(libs.values())]

    netpins = {}
    for p in PARTS:
        pins = pinmaps[p["lib_id"]]
        for num in p["nets"]:
            if num not in pins:
                raise SystemExit(f"{p['ref']}: unknown pin {num}")
        two_pin_vertical = len(pins) == 2 and all(pp["a"] in (90, 270) for pp in pins.values())
        if p["lib_id"] in ("Device:R", "Device:C", "Device:Battery_Cell") or two_pin_vertical:
            rx, ry, vx, vy, just = p["x"] + 2.54, p["y"] - 1.27, p["x"] + 2.54, p["y"] + 1.27, "left"
        else:
            low = 0.0
            for num, pp in pins.items():
                yy = p["y"] - pp["y"]
                if pp["a"] == 90 and p["nets"].get(num):
                    yy += 1.27 * 0.75 * len(p["nets"][num]) + 1.27
                low = max(low, yy)
            low = max(low, p["y"] + 2.54)
            rx, ry, vx, vy, just = p["x"], low + 2.54, p["x"], low + 5.08, None
        node = [Sym("symbol"), [Sym("lib_id"), p["lib_id"]], [Sym("at"), p["x"], p["y"], 0],
                [Sym("unit"), 1], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
                [Sym("dnp"), Sym("yes" if p["dnp"] else "no")], [Sym("uuid"), uid("sym", p["ref"])],
                [Sym("property"), "Reference", p["ref"], [Sym("at"), rx, ry, 0],
                 eff(justify=just)],
                [Sym("property"), "Value", p["value"], [Sym("at"), vx, vy, 0],
                 eff(justify=just)],
                [Sym("property"), "Footprint", p["fp"], [Sym("at"), p["x"], p["y"], 0], eff(hide=True)],
                [Sym("property"), "Datasheet", "", [Sym("at"), p["x"], p["y"], 0], eff(hide=True)],
                [Sym("property"), "MPN", p["mpn"], [Sym("at"), p["x"], p["y"], 0], eff(hide=True)],
                [Sym("property"), "Note", p["note"], [Sym("at"), p["x"], p["y"], 0], eff(hide=True)]]
        for num in pins:
            node.append([Sym("pin"), num, [Sym("uuid"), uid("pin", p["ref"], num)]])
        node.append([Sym("instances"), [Sym("project"), PROJECT,
                                        [Sym("path"), "/" + ROOT_UUID, [Sym("reference"), p["ref"]],
                                         [Sym("unit"), 1]]]])
        sch.append(node)
        for num, pin in pins.items():
            px, py = round(p["x"] + pin["x"], 3), round(p["y"] - pin["y"], 3)
            net = p["nets"].get(num)
            if net:
                netpins.setdefault(net, []).append(f"{p['ref']}.{num}")
                sch.append([Sym("label"), net, [Sym("at"), px, py, LABEL_ANGLE[pin["a"]]],
                            [Sym("fields_autoplaced")], eff(justify=LABEL_JUST[LABEL_ANGLE[pin["a"]]]),
                            [Sym("uuid"), uid("lbl", p["ref"], num)]])
            elif pin["type"] != "no_connect":
                sch.append([Sym("no_connect"), [Sym("at"), px, py], [Sym("uuid"), uid("nc", p["ref"], num)]])
    for i, (x, y, text, size) in enumerate(TEXTS):
        sch.append([Sym("text"), text, [Sym("at"), x, y, 0], eff(size, justify="left bottom"),
                    [Sym("uuid"), uid("txt", i)]])
    sch.append([Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]])
    return sch, netpins


def write_project():
    pro = {"meta": {"filename": PROJECT + ".kicad_pro", "version": 1},
           "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
           "sheets": [[ROOT_UUID, ""]], "text_variables": {}}
    with open(os.path.join(OUT, PROJECT + ".kicad_pro"), "w") as f:
        json.dump(pro, f, indent=2)
    with open(os.path.join(OUT, "fp-lib-table"), "w") as f:
        f.write('(fp_lib_table\n  (version 7)\n  (lib (name "BM83")(type "KiCad")'
                '(uri "${KIPRJMOD}/../lib/BM83.pretty")(options "")(descr "BM83 module footprint"))\n)\n')


def write_bom():
    groups = {}
    for p in PARTS:
        key = (p["lib_id"].split(":")[1], p["value"], p["fp"], p["mpn"], p["dnp"])
        groups.setdefault(key, []).append(p)
    rows = []
    for (sym, val, fp, mpn, dnp), ps in sorted(groups.items(), key=lambda kv: kv[1][0]["ref"]):
        notes = sorted({p["note"] for p in ps if p["note"]})
        rows.append([" ".join(sorted((p["ref"] for p in ps), key=lambda r: (r.rstrip("0123456789o"), r))),
                     len(ps), val, fp.split(":")[1], mpn, "DNP" if dnp else "", " / ".join(notes)])
    with open(os.path.join(OUT, "bom_v0.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Refs", "Qty", "Value", "Footprint", "MPN / 候補", "DNP", "Note"])
        w.writerows(rows)
    return rows


# --------------------------------------------------------------------------
# BM83 footprint (DS70005402H p.57 Fig.8-2)
# --------------------------------------------------------------------------

def write_footprint():
    # Datasheet origin = module bottom-left, +y up. KiCad: +y down, origin at module centre.
    cx, cy = 7.5, 16.0

    def k(x, y):
        return round(x - cx, 3), round(cy - y, 3)

    pads = []
    for i in range(20):  # left column pins 1..20, y = 20.90 .. 1.90
        x, y = k(0.25, 20.90 - i)
        pads.append((str(1 + i), x, y, 1.5, 0.6))
    for i in range(10):  # bottom row pins 21..30, x = 3..12
        x, y = k(3 + i, 0.25)
        pads.append((str(21 + i), x, y, 0.6, 1.5))
    for i in range(20):  # right column pins 31..50, y = 1.90 .. 20.90
        x, y = k(14.75, 1.90 + i)
        pads.append((str(31 + i), x, y, 1.5, 0.6))
    lines = ['(footprint "BM83SM1" (version 20221018) (generator pcbnew) (layer "F.Cu")',
             '  (descr "Microchip BM83SM1 module, DS70005402H Fig.8-2. Pads 56/57 have 0.8mm holes for back-side '
             'hand soldering (v0 option). VERIFY against datasheet before fabrication.")',
             '  (tags "BM83 Bluetooth module")', '  (attr smd)',
             '  (fp_text reference "REF**" (at 0 -17.5) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
             '  (fp_text value "BM83SM1" (at 0 17.5) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))']
    x0, y0 = k(0, 0)
    x1, y1 = k(15, 32)
    lines.append(f'  (fp_rect (start {x0} {y1}) (end {x1} {y0}) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))')
    lines.append(f'  (fp_rect (start {x0 - 0.75} {y1 - 0.25}) (end {x1 + 0.75} {y0 + 0.75}) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))')
    lines.append(f'  (fp_line (start {x0 - 0.3} {k(0, 21.6)[1]}) (end {x0 - 0.3} {y1 - 0.12}) (stroke (width 0.12) (type default)) (layer "F.SilkS"))')
    lines.append(f'  (fp_line (start {x0 - 0.3} {y1 - 0.12}) (end {x1 + 0.3} {y1 - 0.12}) (stroke (width 0.12) (type default)) (layer "F.SilkS"))')
    lines.append(f'  (fp_line (start {x1 + 0.3} {y1 - 0.12}) (end {x1 + 0.3} {k(0, 21.6)[1]}) (stroke (width 0.12) (type default)) (layer "F.SilkS"))')
    lines.append(f'  (fp_circle (center {x0 - 1.2} {k(0, 20.9)[1]}) (end {x0 - 0.9} {k(0, 20.9)[1]}) (stroke (width 0.2) (type default)) (fill solid) (layer "F.SilkS"))')
    # antenna keep-out (no copper on any layer); outline approximated from Fig.8-2 inner lines
    ko = [k(0, 21.4), k(8.9, 21.4), k(8.9, 18), k(13.9, 18), k(13.9, 21.4), k(15, 21.4), k(15, 32), k(0, 32)]
    pts = " ".join(f"(xy {x} {y})" for x, y in ko)
    lines.append('  (zone (net 0) (net_name "") (layers "F&B.Cu" "In1.Cu" "In2.Cu") (hatch edge 0.5) (connect_pads (clearance 0))'
                 ' (min_thickness 0.25) (filled_areas_thickness no)'
                 ' (keepout (tracks not_allowed) (vias not_allowed) (pads not_allowed) (copperpour not_allowed) (footprints not_allowed))'
                 f' (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts {pts})))')
    for num, x, y, w, h in pads:
        lines.append(f'  (pad "{num}" smd rect (at {x} {y}) (size {w} {h}) (layers "F.Cu" "F.Paste" "F.Mask"))')
    x56, y56 = k(12.27, 10.47)
    x57, y57 = k(4.21, 20.58)
    lines.append(f'  (pad "56" thru_hole rect (at {x56} {y56}) (size 1.78 1.78) (drill 0.8) (layers "*.Cu" "F.Paste" "*.Mask"))')
    lines.append(f'  (pad "57" thru_hole rect (at {x57} {y57}) (size 2.79 0.76) (drill oval 1.6 0.4) (layers "*.Cu" "F.Paste" "*.Mask"))')
    lines.append(")")
    os.makedirs(LIBOUT, exist_ok=True)
    with open(os.path.join(LIBOUT, "BM83SM1.kicad_mod"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    sch, netpins = build()
    with open(os.path.join(OUT, PROJECT + ".kicad_sch"), "w", encoding="utf-8") as f:
        f.write(dump(sch) + "\n")
    write_project()
    rows = write_bom()
    write_footprint()
    single = {n: v for n, v in netpins.items() if len(v) < 2}
    print(f"parts={len(PARTS)} nets={len(netpins)} bom_lines={len(rows)}")
    if single:
        print("WARNING single-pin nets:", single)


if __name__ == "__main__":
    main()
