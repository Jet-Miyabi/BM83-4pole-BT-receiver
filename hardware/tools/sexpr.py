"""Minimal S-expression reader/writer for KiCad files."""
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))')


class Sym(str):
    """Unquoted atom."""


def parse(text):
    stack, cur = [], []
    pos = 0
    while True:
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        lp, rp, qs, atom = m.groups()
        if lp:
            stack.append(cur)
            cur = []
        elif rp:
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif qs is not None:
            cur.append(qs[1:-1].replace('\\"', '"').replace('\\\\', '\\'))
        elif atom is not None:
            cur.append(Sym(atom))
    return cur[0] if len(cur) == 1 else cur


def dump(node, indent=0):
    if isinstance(node, list):
        if not node:
            return "()"
        simple = all(not isinstance(x, list) for x in node)
        if simple:
            return "(" + " ".join(dump(x) for x in node) + ")"
        out = "(" + dump(node[0])
        for x in node[1:]:
            if isinstance(x, list):
                out += "\n" + "  " * (indent + 1) + dump(x, indent + 1)
            else:
                out += " " + dump(x)
        return out + ")"
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, (int, float)):
        return fmt_num(node)
    s = str(node).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + s + '"'


def fmt_num(v):
    if isinstance(v, int):
        return str(v)
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]
