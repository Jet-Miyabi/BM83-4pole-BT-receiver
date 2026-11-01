"""Small KiCad 7 schematic generator with wires, power symbols and netlist self-check."""
import copy
import math
import os
import re
import subprocess
import uuid as uuidlib

from sexpr import Sym, dump, find, parse

KISYM = "/usr/share/kicad/symbols"
_NS = uuidlib.UUID("6f1d3c2e-8b1a-4e57-9a51-0000b83a0001")


def uid(*key):
    return str(uuidlib.uuid5(_NS, "/".join(str(k) for k in key)))


def r2(v):
    return round(v + 0.0, 3)


def eff(size=1.27, hide=False, justify=None):
    e = [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]
    if justify:
        e.append([Sym("justify")] + [Sym(j) for j in justify.split()])
    if hide:
        e.append(Sym("hide"))
    return e


# ---------------------------------------------------------------- library symbols
_libcache = {}


def _load_lib(lib):
    if lib not in _libcache:
        with open(os.path.join(KISYM, lib + ".kicad_sym"), encoding="utf-8") as f:
            tree = parse(f.read())
        _libcache[lib] = {n[1]: n for n in find(tree, "symbol")}
    return _libcache[lib]


def lib_symbol(lib_id):
    lib, name = lib_id.split(":")
    syms = _load_lib(lib)
    node = copy.deepcopy(syms[name])
    ext = find(node, "extends")
    if ext:
        parent = copy.deepcopy(syms[ext[0][1]])
        for sub in find(parent, "symbol"):
            if sub[1].startswith(parent[1] + "_"):
                sub[1] = name + sub[1][len(parent[1]):]
        props = find(node, "property")
        body = [x for x in parent[2:] if not (isinstance(x, list) and x and x[0] == "property")]
        node = [Sym("symbol"), name] + props + body
    node[1] = lib_id
    return node, pins_of(node)


def pins_of(node):
    pins = {}
    for sub in find(node, "symbol"):
        for p in find(sub, "pin"):
            at = find(p, "at")[0]
            num = find(p, "number")[0][1]
            pins[num] = dict(x=float(at[1]), y=float(at[2]), a=int(float(at[3])), type=str(p[1]))
    return pins


def xform(px, py, rot):
    """Library pin coordinate -> schematic offset (verified with kicad-cli for 0/90/180/270)."""
    x, y = px, -py
    t = math.radians(rot)
    return r2(x * math.cos(t) + y * math.sin(t)), r2(-x * math.sin(t) + y * math.cos(t))


def pin_dir(a, rot):
    """Direction (dx, dy) in schematic coords pointing from the pin end AWAY from the body."""
    away = {0: (-1, 0), 180: (1, 0), 90: (0, -1), 270: (0, 1)}[a % 360]  # lib coords, y up
    dx, dy = xform(away[0], away[1], rot)
    return round(dx), round(dy)


# ---------------------------------------------------------------- schematic model
class Schematic:
    def __init__(self, project, title, paper="A2"):
        self.project, self.title, self.paper = project, title, paper
        self.root = uid("root")
        self.libs, self.pinmaps = {}, {}
        self.parts, self.wires, self.labels, self.powers, self.texts = [], [], [], [], []
        self.custom = {}

    def add_custom_symbol(self, lib_id, node):
        self.custom[lib_id] = node

    def _sym(self, lib_id):
        if lib_id not in self.libs:
            node = copy.deepcopy(self.custom[lib_id]) if lib_id in self.custom else lib_symbol(lib_id)[0]
            self.libs[lib_id] = node
            self.pinmaps[lib_id] = pins_of(node)
        return self.pinmaps[lib_id]

    # -- parts
    def part(self, ref, lib_id, value, fp, x, y, rot=0, nets=None, dnp=False, mpn="", note="", refpos=None):
        pins = self._sym(lib_id)
        p = dict(ref=ref, lib_id=lib_id, value=value, fp=fp, x=r2(x), y=r2(y), rot=rot, nets=nets or {},
                 dnp=dnp, mpn=mpn, note=note, refpos=refpos)
        for n in p["nets"]:
            if n not in pins:
                raise SystemExit(f"{ref}: unknown pin {n}")
        self.parts.append(p)
        return p

    def pin(self, ref, num):
        p = next(q for q in self.parts if q["ref"] == ref)
        pp = self.pinmaps[p["lib_id"]][num]
        dx, dy = xform(pp["x"], pp["y"], p["rot"])
        return r2(p["x"] + dx), r2(p["y"] + dy)

    def pin_away(self, ref, num):
        p = next(q for q in self.parts if q["ref"] == ref)
        pp = self.pinmaps[p["lib_id"]][num]
        return pin_dir(pp["a"], p["rot"])

    # -- drawing primitives
    def _pt(self, q):
        if isinstance(q, tuple) and len(q) == 2 and isinstance(q[0], str):
            return self.pin(*q)
        return r2(q[0]), r2(q[1])

    def wire(self, *pts):
        pts = [self._pt(q) for q in pts]
        for a, b in zip(pts, pts[1:]):
            if a != b:
                if a[0] != b[0] and a[1] != b[1]:
                    raise SystemExit(f"non-orthogonal wire {a}->{b}")
                self.wires.append((a, b))
        return pts[-1]

    def label(self, net, at, angle=0):
        at = self._pt(at)
        self.labels.append((net, at, angle))

    def stub_label(self, net, ref, num, length=2.54):
        """Short wire out of a pin in its natural direction, then a label."""
        x, y = self.pin(ref, num)
        dx, dy = self.pin_away(ref, num)
        end = (r2(x + dx * length), r2(y + dy * length))
        self.wire((x, y), end)
        ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        self.labels.append((net, end, ang))

    def power(self, kind, at, value=None, rot=0):
        """kind: 'GND' or a power lib symbol such as '+BATT', '+2V5'."""
        at = self._pt(at)
        self._sym("power:" + kind)
        self.powers.append(("power:" + kind, value or kind, at, rot))

    def text(self, x, y, s, size=1.8):
        self.texts.append((r2(x), r2(y), s, size))

    # -- connectivity helpers
    def _conn_points(self):
        pts = set()
        for a, b in self.wires:
            pts.add(a)
            pts.add(b)
        for p in self.parts:
            for num in self.pinmaps[p["lib_id"]]:
                pts.add(self.pin(p["ref"], num))
        for _, _, at, _ in self.powers:
            pts.add(at)
        for _, at, _ in self.labels:
            pts.add(at)
        return pts

    def _split_wires(self):
        pts = self._conn_points()
        out = []
        for a, b in self.wires:
            inner = []
            for q in pts:
                if q in (a, b):
                    continue
                if a[0] == b[0] == q[0] and min(a[1], b[1]) < q[1] < max(a[1], b[1]):
                    inner.append(q)
                elif a[1] == b[1] == q[1] and min(a[0], b[0]) < q[0] < max(a[0], b[0]):
                    inner.append(q)
            seq = sorted([a, b] + inner, key=lambda q: (q[0] - a[0]) ** 2 + (q[1] - a[1]) ** 2)
            out += [(s, t) for s, t in zip(seq, seq[1:]) if s != t]
        self.wires = sorted(set(out))

    def _junctions(self):
        deg = {}
        for a, b in self.wires:
            deg[a] = deg.get(a, 0) + 1
            deg[b] = deg.get(b, 0) + 1
        pinpts = {}
        for p in self.parts:
            for num in self.pinmaps[p["lib_id"]]:
                q = self.pin(p["ref"], num)
                pinpts[q] = pinpts.get(q, 0) + 1
        for _, _, at, _ in self.powers:
            pinpts[at] = pinpts.get(at, 0) + 1
        return sorted(q for q, d in deg.items() if d + pinpts.get(q, 0) >= 3)

    # -- emit
    def build(self, extra_title=()):
        self._split_wires()
        connected = set()
        for a, b in self.wires:
            connected |= {a, b}
        connected |= {at for _, at, _ in self.labels} | {at for _, _, at, _ in self.powers}
        sch = [Sym("kicad_sch"), [Sym("version"), Sym("20230121")], [Sym("generator"), Sym("eeschema")],
               [Sym("uuid"), self.root], [Sym("paper"), self.paper],
               [Sym("title_block"), [Sym("title"), self.title]] + [list(x) for x in extra_title],
               [Sym("lib_symbols")] + list(self.libs.values())]
        for i, (a, b) in enumerate(self.wires):
            sch.append([Sym("wire"), [Sym("pts"), [Sym("xy"), a[0], a[1]], [Sym("xy"), b[0], b[1]]],
                        [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                        [Sym("uuid"), uid("w", a, b)]])
        for q in self._junctions():
            sch.append([Sym("junction"), [Sym("at"), q[0], q[1]], [Sym("diameter"), 0],
                        [Sym("color"), 0, 0, 0, 0], [Sym("uuid"), uid("j", q)]])
        just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}
        for net, at, ang in self.labels:
            sch.append([Sym("label"), net, [Sym("at"), at[0], at[1], ang], [Sym("fields_autoplaced")],
                        eff(justify=just[ang]), [Sym("uuid"), uid("l", net, at)]])
        for i, (lib_id, value, at, rot) in enumerate(self.powers):
            ref = f"#PWR{i + 1:03d}"
            down = lib_id == "power:GND"
            vy = at[1] + (5.08 if down else -3.81)
            node = [Sym("symbol"), [Sym("lib_id"), lib_id], [Sym("at"), at[0], at[1], rot], [Sym("unit"), 1],
                    [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")], [Sym("dnp"), Sym("no")],
                    [Sym("uuid"), uid("pwr", i, at)],
                    [Sym("property"), "Reference", ref, [Sym("at"), at[0], at[1], 0], eff(hide=True)],
                    [Sym("property"), "Value", value, [Sym("at"), at[0], vy, 0], eff()],
                    [Sym("property"), "Footprint", "", [Sym("at"), at[0], at[1], 0], eff(hide=True)],
                    [Sym("property"), "Datasheet", "", [Sym("at"), at[0], at[1], 0], eff(hide=True)],
                    [Sym("pin"), "1", [Sym("uuid"), uid("pwrpin", i)]],
                    [Sym("instances"), [Sym("project"), self.project,
                                        [Sym("path"), "/" + self.root, [Sym("reference"), ref], [Sym("unit"), 1]]]]]
            sch.append(node)
        for p in self.parts:
            pins = self.pinmaps[p["lib_id"]]
            if p["refpos"]:
                (rx, ry, rj), (vx, vy, vj) = p["refpos"]
            else:
                rx, ry, rj, vx, vy, vj = p["x"] + 2.54, p["y"] - 1.27, "left", p["x"] + 2.54, p["y"] + 1.27, "left"
            fang = 90 if p["rot"] % 180 == 90 else 0
            node = [Sym("symbol"), [Sym("lib_id"), p["lib_id"]], [Sym("at"), p["x"], p["y"], p["rot"]],
                    [Sym("unit"), 1], [Sym("in_bom"), Sym("yes")], [Sym("on_board"), Sym("yes")],
                    [Sym("dnp"), Sym("yes" if p["dnp"] else "no")], [Sym("uuid"), uid("sym", p["ref"])],
                    [Sym("property"), "Reference", p["ref"], [Sym("at"), r2(rx), r2(ry), fang], eff(justify=rj)],
                    [Sym("property"), "Value", p["value"], [Sym("at"), r2(vx), r2(vy), fang], eff(justify=vj)],
                    [Sym("property"), "Footprint", p["fp"], [Sym("at"), p["x"], p["y"], 0], eff(hide=True)],
                    [Sym("property"), "Datasheet", "", [Sym("at"), p["x"], p["y"], 0], eff(hide=True)],
                    [Sym("property"), "MPN", p["mpn"], [Sym("at"), p["x"], p["y"], 0], eff(hide=True)],
                    [Sym("property"), "Note", p["note"], [Sym("at"), p["x"], p["y"], 0], eff(hide=True)]]
            for num in pins:
                node.append([Sym("pin"), num, [Sym("uuid"), uid("pin", p["ref"], num)]])
            node.append([Sym("instances"), [Sym("project"), self.project,
                                            [Sym("path"), "/" + self.root, [Sym("reference"), p["ref"]],
                                             [Sym("unit"), 1]]]])
            sch.append(node)
            for num, pp in pins.items():
                q = self.pin(p["ref"], num)
                if num not in p["nets"] and pp["type"] != "no_connect" and q not in connected:
                    sch.append([Sym("no_connect"), [Sym("at"), q[0], q[1]], [Sym("uuid"), uid("nc", p["ref"], num)]])
        for i, (x, y, s, size) in enumerate(self.texts):
            sch.append([Sym("text"), s, [Sym("at"), x, y, 0], eff(size, justify="left bottom"),
                        [Sym("uuid"), uid("t", i)]])
        sch.append([Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]])
        return dump(sch) + "\n"

    # -- verification
    def intended_partition(self):
        nets = {}
        for p in self.parts:
            for num, net in p["nets"].items():
                nets.setdefault(net, set()).add(f"{p['ref']}.{num}")
        return nets

    def verify(self, sch_path, net_path):
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", net_path, sch_path],
                       check=True, capture_output=True)
        t = open(net_path, encoding="utf-8").read()
        got = {}
        for name, body in re.findall(r'\(net \(code "?\d+"?\) \(name "([^"]*)"\)(.*?)\)\s*(?=\(net |\)\s*\)\s*$)',
                                     t, re.S):
            nodes = {f"{r}.{n}" for r, n in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', body)}
            if nodes:
                got[name] = nodes
        want = self.intended_partition()
        want_sets = {frozenset(v): k for k, v in want.items()}
        errors = []
        got_by_pin = {}
        for name, nodes in got.items():
            for n in nodes:
                got_by_pin[n] = name
            fs = frozenset(nodes)
            if fs in want_sets:
                exp = want_sets[fs]
                short = name.lstrip("/")
                if not short.startswith("Net-(") and short != exp:
                    errors.append(f"net name mismatch: got {name} expected {exp}")
                continue
            if len(nodes) == 1 and next(iter(nodes)) not in {x for v in want.values() for x in v}:
                continue  # intentional NC
            errors.append(f"unexpected net {name}: {sorted(nodes)}")
        for net, nodes in want.items():
            if frozenset(nodes) not in {frozenset(v) for v in got.values()}:
                errors.append(f"intended net {net} not reproduced: {sorted(nodes)}")
        return errors
