#!/usr/bin/env python3
"""Generate the KiCad 7 schematic (with wires), BOM and BM83 footprint for dev board v0.

This script is the single source of truth for the v0 design. Each part carries its
intended nets; the drawing (wires / power symbols / labels) is then checked against
those nets by exporting the netlist with kicad-cli. Any mismatch aborts the run.

    python3 hardware/tools/gen_v0.py

Outputs (relative to repo root):
    hardware/bm83_rx_v0/bm83_rx_v0.kicad_sch / .kicad_pro / .net / fp-lib-table / bom_v0.csv
    hardware/lib/BM83.pretty/BM83SM1.kicad_mod
"""
import csv
import json
import os
import sys

from kigen import Schematic
from sexpr import Sym

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "hardware", "bm83_rx_v0")
LIBOUT = os.path.join(ROOT, "hardware", "lib", "BM83.pretty")
PROJECT = "bm83_rx_v0"

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


# ==========================================================================
# Design + drawing
# ==========================================================================
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

sch = Schematic(PROJECT, "BM83 throat-mic BT receiver - dev board v0")
sch.add_custom_symbol("BM83_Project:BM83SM1", bm83_symbol()[0])


def _vbat_power_symbol():
    """power:+BATT cloned as power:VBAT (KiCad 7 takes the net name from the hidden pin name)."""
    import copy
    from kigen import lib_symbol
    from sexpr import find
    node = copy.deepcopy(lib_symbol("power:+BATT")[0])
    node[1] = "power:VBAT"
    for prop in find(node, "property"):
        if prop[1] == "Value":
            prop[2] = "VBAT"
    for sub in find(node, "symbol"):
        sub[1] = sub[1].replace("+BATT", "VBAT")
        for pin in find(sub, "pin"):
            find(pin, "name")[0][1] = "VBAT"
    return node


sch.add_custom_symbol("power:VBAT", _vbat_power_symbol())
ROOT_UUID = sch.root
PARTS = sch.parts
W = sch.wire


def gnd(pt):
    sch.power("GND", pt)


def vbat(pt):
    sch.power("VBAT", pt)


def v25(pt):
    sch.power("+2V5", pt)


def V(ref, lib, val, fp, x, y, n1, n2, **kw):
    """Vertical 2-pin part: pin 1 at top (y-3.81), pin 2 at bottom (y+3.81)."""
    return sch.part(ref, lib, val, fp, x, y, 0, {"1": n1, "2": n2}, **kw)


def H(ref, lib, val, fp, x, y, n1, n2, **kw):
    """Horizontal 2-pin part: pin 1 left (x-3.81), pin 2 right (x+3.81)."""
    return sch.part(ref, lib, val, fp, x, y, 90, {"1": n1, "2": n2},
                    refpos=((x, y - 2.54, None), (x, y + 2.79, None)), **kw)


def Rv(ref, val, x, y, n1, n2, **kw):
    return V(ref, "Device:R", val, FP_R, x, y, n1, n2, **kw)


def Cv(ref, val, x, y, n1, n2, fp=FP_C, **kw):
    return V(ref, "Device:C", val, fp, x, y, n1, n2, **kw)


def Rh(ref, val, x, y, n1, n2, **kw):
    return H(ref, "Device:R", val, FP_R, x, y, n1, n2, **kw)


def Ch(ref, val, x, y, n1, n2, fp=FP_C, **kw):
    return H(ref, "Device:C", val, fp, x, y, n1, n2, **kw)


def shunt_gnd(ref):
    """Pin 2 of a vertical part to a GND symbol."""
    gnd(sch.pin(ref, "2"))


def header_labels(ref):
    p = next(q for q in sch.parts if q["ref"] == ref)
    for num, net in p["nets"].items():
        if net == "GND":
            x, y = sch.pin(ref, num)
            dx, dy = sch.pin_away(ref, num)
            ln = 10.16 if "01x" in p["lib_id"] else 2.54
            end = (x + dx * ln, y + dy * ln)
            W((x, y), end)
            gnd(end)
        else:
            sch.stub_label(net, ref, num)


# ---------------------------------------------------------------- POWER
sch.text(25.4, 33.02, "POWER: 14500 Li-ion (4.2V cells only) -> reverse-polarity P-FET Q1 -> SW1 -> VBAT", 2.0)
sch.part("BT1", "Device:Battery_Cell", "14500 Li-ion", "Battery:BatteryHolder_Keystone_2460_1xAA",
         30.48, 55.88, 0, {"1": "BAT_RAW", "2": "GND"},
         mpn="Keystone 2460 (要: 保護付きセルの長さ適合確認)", note="4.35V高電圧セル/LiFePO4不可",
         refpos=((34.29, 54.61, "left"), (34.29, 57.15, "left")))
gnd(sch.pin("BT1", "2"))
sch.part("Q1", "Device:Q_PMOS_GSD", "AO3401A", FP_SOT23, 50.8, 48.26, 90,
         {"1": "Q1_G", "2": "VBAT_P", "3": "BAT_RAW"}, mpn="AO3401A", note="逆接続保護: D=電池側, S=負荷側",
         refpos=((50.8, 40.64, None), (50.8, 38.1, None)))
W(("BT1", "1"), (30.48, 45.72), ("Q1", "3"))
Rv("R1", "100k", 50.8, 57.15, "Q1_G", "GND")
shunt_gnd("R1")
sch.part("SW1", "Switch:SW_SPDT", "POWER", "Button_Switch_SMD:SW_SPDT_PCM12", 66.04, 45.72, 0,
         {"2": "VBAT_P", "1": "VBAT"}, mpn="C&K PCM12SMTR",
         refpos=((66.04, 39.37, None), (66.04, 52.07, None)))
W(("Q1", "2"), ("SW1", "2"))
rail = W(("SW1", "1"), (111.76, 43.18))
vbat((78.74, 43.18))
Cv("C1", "10u", 86.36, 46.99, "VBAT", "GND", fp=FP_C08, note="U1 BAT_IN直近")
Cv("C2", "10u", 96.52, 46.99, "VBAT", "GND", fp=FP_C08, note="U2 BAT_IN直近")
Cv("C3", "100n", 106.68, 46.99, "VBAT", "GND")
for c in ("C1", "C2", "C3"):
    shunt_gnd(c)

# ---------------------------------------------------------------- ANALOG FRONT END
sch.text(25.4, 81.28, "MIC BIAS (always-on 2.5V, so PTT can be detected while idle) / JACK / MIC INPUT / PTT DETECT", 2.0)
# LDO
sch.part("U3", "Regulator_Linear:TLV75525PDBV", "TLV75525PDBV", FP_SOT235, 55.88, 96.52, 0,
         {"1": "VBAT", "3": "VBAT", "2": "GND", "5": "+2V5"}, mpn="TI TLV75525PDBVR",
         note="2.5V LDO, Iq≈25µA. 雑音はR2/C5で減衰",
         refpos=((55.88, 87.63, None), (55.88, 90.17, None)))
W((33.02, 93.98), ("U3", "1"))
vbat((33.02, 93.98))
Cv("C4", "1u", 38.1, 97.79, "VBAT", "GND")
shunt_gnd("C4")
W(("U3", "3"), (43.18, 96.52), (43.18, 93.98))
gnd(sch.pin("U3", "2"))
# 2.5V rail -> RC filter -> JP1
W(("U3", "5"), (74.93, 93.98))
W((71.12, 93.98), (71.12, 91.44))
v25((71.12, 91.44))
Cv("C15", "1u", 66.04, 97.79, "+2V5", "GND")
shunt_gnd("C15")
Rh("R2", "1k", 78.74, 93.98, "+2V5", "BIAS_F")
W(("R2", "2"), (93.98, 93.98))
Cv("C5", "10u", 87.63, 97.79, "BIAS_F", "GND", fp=FP_C08, note="R2とでfc≈16Hz")
shunt_gnd("C5")
sch.part("JP1", "Jumper:SolderJumper_3_Open", "BIAS_SEL", FP_SJ3, 99.06, 93.98, 0,
         {"1": "BIAS_F", "2": "BIAS_SEL", "3": "MICBIAS1"},
         note="既定 1-2短絡(自前バイアス)。2-3でBM83 MICBIAS",
         refpos=((99.06, 88.9, None), (99.06, 91.44, None)))
W(("JP1", "3"), (119.38, 93.98))
Cv("C6", "1u", 111.76, 97.79, "MICBIAS1", "GND", note="Microchip ref C22")
shunt_gnd("C6")
sch.label("MICBIAS1", (119.38, 93.98), 0)
Rv("R3", "2.2k", 99.06, 110.49, "BIAS_SEL", "MIC", note="Microchip ref R6=2.2k")
W(("JP1", "2"), ("R3", "1"))
# Jack (pins pointing down: T, R1, R2, S from left to right)
sch.part("J1", "Connector_Audio:AudioJack4", "TRRS CTIA",
         "Connector_Audio:Jack_3.5mm_KoreanHropartsElec_PJ-320D-4A_Horizontal", 22.86, 111.76, 270,
         {"T": "HP_T", "R1": "HP_R", "R2": "MIC_RET", "S": "MIC"},
         mpn="Korean Hroparts PJ-320D-4A (LCSC C95562)",
         refpos=((30.48, 107.95, "left"), (30.48, 110.49, "left")))
MIC_Y, RET_Y = 121.92, 137.16
W(("J1", "S"), (25.4, MIC_Y), (129.54, MIC_Y))                 # MIC trunk
W(("R3", "2"), (99.06, MIC_Y))
W(("J1", "R2"), (22.86, RET_Y), (78.74, RET_Y))                # MIC_RET trunk
W(("J1", "R1"), (20.32, 147.32))
sch.label("HP_R", (20.32, 147.32), 270)
W(("J1", "T"), (17.78, 147.32))
sch.label("HP_T", (17.78, 147.32), 270)
Rv("R4", "0", 40.64, 140.97, "MIC_RET", "GND", note="ジャック直近の1点でGNDへ(ネットタイ)")
shunt_gnd("R4")
Cv("C9", "220p", 48.26, 125.73, "MIC", "MIC_RET", note="Microchip ref C27")
W(("C9", "2"), (48.26, RET_Y))
sch.part("C7", "Device:C", "47n", FP_C, 73.66, 118.11, 180, {"1": "MIC", "2": "MICP1"},
         note="DCカット。100nと比較(V4)", refpos=((76.2, 113.03, "left"), (76.2, 115.57, "left")))
sch.stub_label("MICP1", "C7", "2")
Cv("C8", "47n", 73.66, 140.97, "MIC_RET", "MICN1", note="DCカット。100nと比較(V4)")
sch.stub_label("MICN1", "C8", "2")
sch.text(30.48, 160.02, "J1: T/R1 = air-tube earpiece (via SW4), R2 = mic return, S = MIC (CTIA)", 1.5)
# PTT detect
Rh("R5", "100k", 133.35, MIC_Y, "MIC", "PTT_F")
sch.part("U4", "Comparator:TLV7041DBV", "TLV7041DBV", FP_SOT235, 165.1, 124.46, 0,
         {"3": "PTT_F", "4": "PTT_TH", "1": "PTT_N", "5": "+2V5", "2": "GND"}, mpn="TI TLV7041DBVR",
         note="ナノパワー, オープンドレイン出力",
         refpos=((170.18, 132.08, "left"), (170.18, 134.62, "left")))
W(("R5", "2"), ("U4", "3"))
Cv("C10", "100n", 139.7, 125.73, "PTT_F", "GND", note="τ=10ms 音声成分除去")
shunt_gnd("C10")
W(("U4", "4"), (154.94, 127.0), (154.94, 134.62))
Rh("R6", "2.2M", 148.59, 134.62, "+2V5", "PTT_TH")
W(("R6", "2"), (154.94, 134.62))
v25(sch.pin("R6", "1"))
Rv("R7", "390k", 154.94, 138.43, "PTT_TH", "GND", note="Vth≈0.38V",
   refpos=((152.4, 137.16, "right"), (152.4, 139.7, "right")))
shunt_gnd("R7")
gnd(sch.pin("U4", "2"))
W(("U4", "5"), (162.56, 109.22), (177.8, 109.22))
v25((170.18, 109.22))
Cv("C11", "100n", 177.8, 113.03, "+2V5", "GND")
shunt_gnd("C11")
W(("U4", "1"), (218.44, 124.46))
sch.label("PTT_N", (218.44, 124.46), 0)
# hysteresis loop (DNP)
W((185.42, 124.46), (185.42, 99.06), (172.72, 99.06))
Rh("R8", "10M", 168.91, 99.06, "PTT_F", "PTT_N", dnp=True, note="ヒステリシス用(DNP)")
W(("R8", "1"), (152.4, 99.06), (152.4, MIC_Y))
sch.part("SW2", "Switch:SW_Push", "PLAY(test)", FP_SW, 193.04, 129.54, 270, {"1": "PTT_N", "2": "GND"},
         note="PTTと並列の試験用ボタン", refpos=((190.5, 144.78, None), (190.5, 147.32, None)))
gnd(sch.pin("SW2", "2"))
sch.part("D1", "Device:D_TVS", "PESD5V0S1BA", FP_TVS, 203.2, 128.27, 270, {"1": "PTT_N", "2": "GND"},
         mpn="Nexperia PESD5V0S1BA", refpos=((205.74, 144.78, None), (205.74, 147.32, None)))
gnd(sch.pin("D1", "2"))
Cv("C12", "15p", 213.36, 128.27, "PTT_N", "GND", note="Microchip ref ボタン入力")
shunt_gnd("C12")
sch.text(132.08, 152.4, "PTT shorts MIC to GND (1.25 ohm measured) -> PTT_N low -> U1 P0_2 (default PLAY/PAUSE)", 1.5)


# ---------------------------------------------------------------- BM83 modules
def bm83(ref, value, X, Y, nets, mpn, note=""):
    sch.part(ref, "BM83_Project:BM83SM1", value, "BM83:BM83SM1", X, Y, 0, nets, mpn=mpn, note=note,
             refpos=((X, Y - 43.18, None), (X, Y - 40.64, None)))
    gnd_pins = [n for n, net in nets.items() if net == "GND"]
    pts = []
    for n in gnd_pins:
        x, y = sch.pin(ref, n)
        W((x, y), (x - 2.54, y))
        pts.append((x - 2.54, y))
    pts.sort(key=lambda q: q[1])
    W(pts[0], (pts[0][0], pts[-1][1] + 2.54))
    gnd((pts[0][0], pts[-1][1] + 2.54))
    for n, net in nets.items():
        if net == "GND":
            continue
        if net == "VBAT":
            x, y = sch.pin(ref, n)
            W((x, y), (x - 5.08, y))
            vbat((x - 5.08, y))
            continue
        x, y = sch.pin(ref, n)
        dx, _ = sch.pin_away(ref, n)
        sch.label(net, (x, y), 180 if dx < 0 else 0)


def bm83_support(idx, X0, Y0):
    """MFB switch, LEDs, ADAP_IN cap, programming header for module idx (1 or 2)."""
    s = str(idx)
    sw, d_esd, c_esd, led_a, led_b, c_adap, jprog = {
        1: ("SW3", "D2", "C14", "D3", "D4", "C13", "J2"),
        2: ("SW5", "D5", "C31", "D6", "D7", "C30", "J3")}[idx]
    # MFB
    sch.part(sw, "Switch:SW_Push", f"MFB{s}", FP_SW, X0 + 7.62, Y0, 0, {"1": f"SYSPWR{s}", "2": f"MFB{s}"},
             note="MFBはSYS_PWRへ引上げ(アクティブハイ)" if idx == 1 else "長押しでOpenRun探索",
             refpos=((X0 + 7.62, Y0 - 5.08, None), (X0 + 7.62, Y0 - 3.81 + 6.35, None)))
    sch.stub_label(f"SYSPWR{s}", sw, "1")
    W((sw, "2"), (X0 + 33.02, Y0))
    sch.label(f"MFB{s}", (X0 + 33.02, Y0), 0)
    sch.part(d_esd, "Device:D_TVS", "PESD5V0S1BA", FP_TVS, X0 + 17.78, Y0 + 3.81, 270,
             {"1": f"MFB{s}", "2": "GND"}, mpn="Nexperia PESD5V0S1BA",
             refpos=((X0 + 15.24, Y0 + 13.97, None), (X0 + 15.24, Y0 + 16.51, None)))
    gnd(sch.pin(d_esd, "2"))
    Cv(c_esd, "15p", X0 + 27.94, Y0 + 3.81, f"MFB{s}", "GND")
    shunt_gnd(c_esd)
    # LEDs (anode = SYS_PWR, cathode = LED driver pin)
    ly = Y0 + 25.4
    for k, (d, col, net) in enumerate(((led_a, "RED", f"LED{s}A"), (led_b, "BLUE", f"LED{s}B"))):
        y = ly + k * 10.16
        sch.part(d, "Device:LED", col, FP_LED, X0 + 12.7, y, 180, {"2": f"SYSPWR{s}", "1": net},
                 note="LEDドライバ直結(電流はConfigで設定)" if k == 0 else "",
                 refpos=((X0 + 12.7, y - 3.81, None), (X0 + 12.7, y + 2.54, None)))
        W((d, "2"), (X0 + 5.08, y))
        sch.stub_label(net, d, "1")
    W((X0 + 5.08, ly), (X0 + 5.08, ly + 10.16))
    W((X0 + 5.08, ly), (X0 + 5.08, ly - 2.54))
    sch.label(f"SYSPWR{s}", (X0 + 5.08, ly - 2.54), 90)
    # ADAP_IN cap
    Cv(c_adap, "10u", X0 + 33.02, ly + 3.81, f"ADAP{s}", "GND", fp=FP_C08,
       note="Microchip ref C31")
    sch.stub_label(f"ADAP{s}", c_adap, "1")
    shunt_gnd(c_adap)
    # programming header
    sch.part(jprog, "Connector_Generic:Conn_01x06", f"PROG{s}", FP_H6, X0 + 68.58, ly + 2.54, 0,
             {"1": f"CFG{s}", "2": "GND", "3": f"TX{s}", "4": f"RX{s}", "5": f"ADAP{s}", "6": f"RST{s}"},
             note="1-2ジャンパ=Test mode。書込時は電池OFFでADAP_INに5V" if idx == 1 else "",
             refpos=((X0 + 68.58, ly - 7.62, None), (X0 + 68.58, ly - 5.08, None)))
    header_labels(jprog)


sch.text(289.56, 33.02, "U1: BM83 #1  standard FW (Embedded) - HFP/A2DP sink, throat mic", 2.0)
U1 = {"23": "VBAT", "22": "ADAP1", "24": "SYSPWR1", "26": "MFB1", "43": "RST1",
      "14": "MICP1", "13": "MICN1", "15": "MICBIAS1", "8": "HPL1", "6": "HPR1",
      "32": "LED1A", "34": "LED1B", "16": "GND", "50": "GND", "56": "GND", "57": "GND",
      "30": "TX1", "29": "RX1", "31": "CFG1", "33": "PTT_N",
      "48": "U1_P3_7", "49": "U1_P0_0", "44": "U1_P0_1", "38": "U1_P0_3", "40": "U1_P0_5",
      "35": "U1_P0_6", "45": "U1_P0_7", "46": "U1_P1_2", "47": "U1_P1_3", "41": "U1_P1_6",
      "42": "LINK_EN", "21": "U1_P2_6", "39": "U1_P2_7", "20": "U1_P3_2",
      "1": "U1_DR1", "2": "U1_RFS1", "3": "U1_SCLK1", "4": "U1_DT1", "5": "U1_MCLK1"}
bm83("U1", "BM83SM1-00AA", 330.2, 99.06, U1, "Microchip BM83SM1-00AA / -00AB",
     note="AOHPM未接続(Single-End)")
bm83_support(1, 292.1, 160.02)
sch.part("J4", "Connector_Generic:Conn_02x08_Odd_Even", "GPIO1", FP_H16, 312.42, 223.52, 0,
         {"1": "U1_P0_0", "2": "U1_P0_1", "3": "U1_P0_3", "4": "U1_P0_5", "5": "U1_P0_6", "6": "U1_P0_7",
          "7": "U1_P1_2", "8": "U1_P1_3", "9": "U1_P1_6", "10": "LINK_EN", "11": "U1_P2_6", "12": "U1_P2_7",
          "13": "U1_P3_2", "14": "U1_P3_7", "15": "GND", "16": "GND"},
         refpos=((312.42, 210.82, None), (312.42, 213.36, None)))
header_labels("J4")
sch.part("J5", "Connector_Generic:Conn_01x06", "I2S1", FP_H6, 365.76, 223.52, 0,
         {"1": "U1_DR1", "2": "U1_RFS1", "3": "U1_SCLK1", "4": "U1_DT1", "5": "U1_MCLK1", "6": "GND"},
         note="I2S連携の実験用", refpos=((365.76, 210.82, None), (365.76, 213.36, None)))
header_labels("J5")

sch.text(449.58, 33.02, "U2: BM83 #2  AT FW (Embedded) - A2DP source to Shokz OpenRun", 2.0)
U2 = {"23": "VBAT", "22": "ADAP2", "24": "SYSPWR2", "26": "MFB2", "43": "RST2",
      "12": "AIL2", "11": "AIR2", "32": "LED2A", "34": "LED2B",
      "16": "GND", "50": "GND", "56": "GND", "57": "GND",
      "30": "TX2", "29": "RX2", "31": "CFG2", "20": "AUXDET2",
      "48": "U2_P3_7", "49": "U2_P0_0", "44": "U2_P0_1", "33": "U2_P0_2", "38": "U2_P0_3",
      "40": "U2_P0_5", "35": "U2_P0_6", "45": "U2_P0_7", "46": "U2_P1_2", "47": "U2_P1_3",
      "41": "U2_P1_6", "42": "U2_P2_3", "21": "U2_P2_6", "39": "U2_P2_7",
      "1": "U2_DR1", "2": "U2_RFS1", "3": "U2_SCLK1", "4": "U2_DT1", "5": "U2_MCLK1"}
bm83("U2", "BM83SM1-00TA", 492.76, 99.06, U2, "Microchip BM83SM1-00TA (AT FW書込済の情報あり, 要確認)")
bm83_support(2, 454.66, 160.02)
sch.part("J6", "Connector_Generic:Conn_02x08_Odd_Even", "GPIO2", FP_H16, 474.98, 223.52, 0,
         {"1": "U2_P0_0", "2": "U2_P0_1", "3": "U2_P0_2", "4": "U2_P0_3", "5": "U2_P0_5", "6": "U2_P0_6",
          "7": "U2_P0_7", "8": "U2_P1_2", "9": "U2_P1_3", "10": "U2_P1_6", "11": "U2_P2_3", "12": "U2_P2_6",
          "13": "U2_P2_7", "14": "U2_P3_7", "15": "GND", "16": "GND"},
         note="AT FWの送信/受信・入力切替GPIOをここでGNDへ",
         refpos=((474.98, 210.82, None), (474.98, 213.36, None)))
header_labels("J6")
sch.part("J7", "Connector_Generic:Conn_01x06", "I2S2", FP_H6, 528.32, 223.52, 0,
         {"1": "U2_DR1", "2": "U2_RFS1", "3": "U2_SCLK1", "4": "U2_DT1", "5": "U2_MCLK1", "6": "GND"},
         refpos=((528.32, 210.82, None), (528.32, 213.36, None)))
header_labels("J7")
# Aux-in detect select for U2
sch.text(449.58, 251.46, "U2 Aux-in detect (P3_2): JP2 1-2 = always detected, 2-3 = follow U1 LINK_EN (D11, unverified)", 1.5)
sch.part("JP2", "Jumper:SolderJumper_3_Open", "AUXDET_SEL", FP_SJ3, 474.98, 264.16, 0,
         {"1": "GND", "2": "AUXDET2", "3": "LINK_EN_R"},
         note="1-2: Aux常時検出 / 2-3: U1 GPIO連動(D11案)",
         refpos=((474.98, 259.08, None), (474.98, 256.54, None)))
W(("JP2", "1"), (464.82, 264.16), (464.82, 266.7))
gnd((464.82, 266.7))
sch.stub_label("AUXDET2", "JP2", "2")
Rh("R18", "1k", 488.95, 264.16, "LINK_EN_R", "LINK_EN")
W(("JP2", "3"), ("R18", "1"))
W(("R18", "2"), (497.84, 264.16))
sch.label("LINK_EN", (497.84, 264.16), 0)

# ---------------------------------------------------------------- AUDIO OUT of U1
sch.text(25.4, 236.22, "U1 AUDIO OUT (Config: Speaker Output = Single End) -> line to U2 Aux-in  /  -> SW4 -> air-tube earpiece", 2.0)
for i, (ch, src, dst) in enumerate([("L", "HPL1", "AIL2"), ("R", "HPR1", "AIR2")]):
    y = 254.0 + i * 25.4
    n = 20 + i * 3
    m = 10 + i * 3
    sch.label(src, (30.48, y), 180)
    Ch(f"C{n}", "4.7u", 40.64, y, src, f"LINE{ch}_A", fp=FP_C08)
    W((30.48, y), (f"C{n}", "1"))
    W((f"C{n}", "2"), (55.88, y))
    Rv(f"R{m}", "10k", 50.8, y + 3.81, f"LINE{ch}_A", "GND")
    shunt_gnd(f"R{m}")
    Rh(f"R{m + 1}", "1k", 59.69, y, f"LINE{ch}_A", f"LINE{ch}_B")
    W((f"R{m + 1}", "2"), (76.2, y))
    Cv(f"C{n + 1}", "470p", 68.58, y + 3.81, f"LINE{ch}_B", "GND", note="Microchip ref Aux入力")
    shunt_gnd(f"C{n + 1}")
    Ch(f"C{n + 2}", "10u", 80.01, y, f"LINE{ch}_B", dst, fp=FP_C08, note="Microchip ref C5/C7")
    W((f"C{n + 2}", "2"), (88.9, y))
    sch.label(dst, (88.9, y), 0)
sch.label("HPL1", (110.49, 254.0), 180)
Ch("C26", "100u", 120.65, 254.0, "HPL1", "HPL_J", fp=FP_C12, note="DCカット 32Ωでfc≈50Hz")
W((110.49, 254.0), ("C26", "1"))
sch.label("HPR1", (110.49, 264.16), 180)
Ch("C27", "100u", 120.65, 264.16, "HPR1", "HPR_J", fp=FP_C12)
W((110.49, 264.16), ("C27", "1"))
sch.part("SW4", "Switch:SW_DIP_x02", "EARPIECE",
         "Button_Switch_SMD:SW_DIP_SPSTx02_Slide_6.7x6.64mm_W8.61mm_P2.54mm_LowProfile",
         139.7, 256.54, 0, {"1": "HPL_J", "4": "HP_T", "2": "HPR_J", "3": "HP_R"},
         note="ON=エアチューブイヤホンへ出力",
         refpos=((139.7, 245.11, None), (139.7, 247.65, None)))
W(("C26", "2"), ("SW4", "1"))
W(("C27", "2"), (129.54, 264.16), (129.54, 256.54), ("SW4", "2"))
W(("SW4", "4"), (165.1, 254.0))
sch.label("HP_T", (165.1, 254.0), 0)
Rv("R16", "10k", 157.48, 257.81, "HP_T", "GND", note="ポップ低減ブリーダ")
shunt_gnd("R16")
W(("SW4", "3"), (149.86, 256.54), (149.86, 269.24), (165.1, 269.24))
sch.label("HP_R", (165.1, 269.24), 0)
Rv("R17", "10k", 160.02, 273.05, "HP_R", "GND")
shunt_gnd("R17")

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
    sch_path = os.path.join(OUT, PROJECT + ".kicad_sch")
    with open(sch_path, "w", encoding="utf-8") as f:
        f.write(sch.build(extra_title=[
            [Sym("date"), "2026-11-01"], [Sym("rev"), "v0.2"],
            [Sym("comment"), 1, "Generated by hardware/tools/gen_v0.py - edit the script, not this file"],
            [Sym("comment"), 2, "Values marked 仮/要確認 in BOM must be verified before ordering"]]))
    write_project()
    rows = write_bom()
    write_footprint()
    errors = sch.verify(sch_path, os.path.join(OUT, PROJECT + ".net"))
    print(f"parts={len(PARTS)} wires={len(sch.wires)} bom_lines={len(rows)}")
    if errors:
        print("NETLIST CHECK FAILED:")
        for e in errors:
            print("  ", e)
        sys.exit(1)
    print("netlist check: OK (drawing reproduces the intended nets)")


if __name__ == "__main__":
    main()
