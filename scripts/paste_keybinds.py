#!/usr/bin/python3
"""ChillPill-Shell managed keybinds for niri (config.kdl).

Modes:
  paste <block> [path]   write the managed binds file and include it from config.kdl
  remove [path]          strip the include and delete the managed binds file
  check [path]           JSON report: per-state combo/expr, old lines, duplicate combos

[path] is the niri config file (default: $XDG_CONFIG_HOME/niri/config.kdl).

The generated binds live in chillpill-binds.kdl next to config.kdl. config.kdl
only gets a marked block containing  include "chillpill-binds.kdl"  at the end
of the file. niri merges `binds` from included files and an include overrides
earlier binds on the same key (niri 25.11 or newer), so the shell's combos win
over niri's defaults such as Mod+D.

A "chillpill bind" is any single-line bind in config.kdl whose spawn command
mentions the shell, e.g.
  Mod+D { spawn "qs" "ipc" "-p" "/usr/share/chillpill-shell" "call" "spotlight" "toggle"; }
  Mod+D { spawn "chillpill-shell-ipc" "call" "spotlight" "toggle"; }
Multi-line binds are not detected. They keep working, because the include
comes last and overrides them.

Paste keeps every existing key combo: each state's combo (and any properties
such as repeat=false) is carried into the managed file; defaults are only used
for states without a bind. Old/duplicate chillpill binds for the same state
are removed from config.kdl so each state stays bound exactly once.
"""

import json
import os
import re
import sys

HEAD = "// >>> chillpill-shell keybinds (managed)"
TAIL = "// <<< chillpill-shell keybinds"
BINDS_FILE = "chillpill-binds.kdl"
INCLUDE_LINE = 'include "%s"' % BINDS_FILE
STATES = ["controlCenter", "cliphist", "dashboard", "spotlight", "wallpaperSwitcher", "powerMenu", "wifiState", "bluetoothState", "theme"]
STATE_SET = set(STATES)
BIND_RE = re.compile(r'^\s*(?P<expr>[^\s{}/][^{}]*?)\s*\{\s*spawn(?:-sh)?\s+(?P<args>[^}]*?)\s*;?\s*\}')
STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
IPC_RE = re.compile(r'(?:-p\s+\S*chillpill-shell\S*|chillpill-shell-ipc).*?call\s+(\w+)\s+(?:toggle|show|hide)')


def get_path(mode):
    # paste takes <block> [path]; check/remove take [path]
    idx = 3 if mode == "paste" else 2
    if len(sys.argv) > idx and not sys.argv[idx].startswith("--"):
        return sys.argv[idx]
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "niri", "config.kdl")


def binds_path(cfg):
    return os.path.join(os.path.dirname(cfg), BINDS_FILE)


def read_lines(path):
    if not os.path.exists(path):
        return []
    text = open(path).read()
    return text.split("\n") if text else []


def write_lines(path, lines):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    open(path, "w").write("\n".join(lines).strip() + "\n")


def parse_bind(line):
    if line.strip().startswith("//"):
        return None
    m = BIND_RE.match(line)
    if not m:
        return None
    expr = m.group("expr").strip()
    cmd = " ".join(STR_RE.findall(m.group("args")))
    mc = IPC_RE.search(cmd)
    return {"combo": expr.split()[0], "state": mc.group(1) if mc else None,
            "expr": expr, "cmd": cmd, "args": m.group("args").strip(),
            "chillpill": bool(mc)}


def collect(lines, managed):
    """Return (line_index, parsed_bind) for every bind in `lines`."""
    out = []
    in_block = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith(HEAD):
            in_block = True
            continue
        if s.startswith(TAIL):
            in_block = False
            continue
        b = parse_bind(ln)
        if b:
            b["managed"] = managed
            out.append((i, b))
    return out


def preferred_exprs(cfg_binds, managed_binds):
    """state -> combo expression the user already has.

    A bind in config.kdl (where manual edits land) wins over the managed
    file, and the last occurrence wins among equals.
    """
    exprs = {}
    for _, b in managed_binds:
        if b["chillpill"] and b["state"] in STATE_SET:
            exprs.setdefault(b["state"], b["expr"])
    for _, b in cfg_binds:
        if b["chillpill"] and b["state"] in STATE_SET:
            exprs[b["state"]] = b["expr"]
    return exprs


def report(cfg_binds, managed_binds):
    pref = preferred_exprs(cfg_binds, managed_binds)
    states = {s: {"count": 0, "managed": False, "combo": "", "expr": pref.get(s, "")} for s in STATES}
    old = []
    for i, b in cfg_binds:
        if b["chillpill"] and b["state"] in STATE_SET:
            states[b["state"]]["count"] += 1
            old.append(i)
    for _, b in managed_binds:
        if b["chillpill"] and b["state"] in STATE_SET:
            r = states[b["state"]]
            r["count"] += 1
            r["managed"] = True
            r["combo"] = b["combo"]
    # niri rejects the same key twice inside one file; across files the
    # later include simply overrides
    dups = {}
    for group in (cfg_binds, managed_binds):
        seen = {}
        for _, b in group:
            seen[b["combo"]] = seen.get(b["combo"], 0) + 1
        for c, n in seen.items():
            if n > 1:
                dups[c] = n
    return {"states": states, "old_lines": old, "dup_combos": dups}


def rebuild_block(block, exprs):
    """Swap each template line's combo expression for the user's."""
    out = [HEAD]
    kept = []
    for ln in block.split("\n"):
        ln = ln.rstrip()
        if not ln or ln.lstrip().startswith("//"):
            continue
        b = parse_bind(ln)
        if not b:
            out.append(ln)
            continue
        use = exprs.get(b["state"]) if b["state"] else None
        if use:
            kept.append(b["state"])
        out.append("    %s { spawn %s; }" % (use or b["expr"], b["args"]))
    out.append(TAIL)
    return out, kept


def strip_managed(lines):
    """Remove the marked include block from config.kdl lines."""
    out, skip = [], False
    for ln in lines:
        s = ln.strip()
        if s.startswith(HEAD):
            skip = True
            continue
        if s.startswith(TAIL):
            skip = False
            continue
        if not skip:
            out.append(ln)
    return out


def load(cfg):
    lines = read_lines(cfg)
    mlines = read_lines(binds_path(cfg))
    return lines, mlines, collect(strip_marked(lines), False), collect(mlines, True)


def strip_marked(lines):
    # keep indices aligned with `lines`: blank out the marked block instead of deleting it
    out, skip = [], False
    for ln in lines:
        s = ln.strip()
        if s.startswith(HEAD):
            skip = True
            out.append("")
            continue
        if s.startswith(TAIL):
            skip = False
            out.append("")
            continue
        out.append("" if skip else ln)
    return out


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "paste").lstrip("-")
    cfg = get_path(mode)
    bpath = binds_path(cfg)
    try:
        lines, mlines, cfg_binds, managed_binds = load(cfg)
    except OSError as e:
        print("error: cannot read %s: %s" % (cfg, e), file=sys.stderr)
        sys.exit(1)

    if mode == "check":
        rep = report(cfg_binds, managed_binds)
        rep["path"] = cfg
        json.dump(rep, sys.stdout, indent=1)
        return

    if mode == "remove":
        had_include = any(l.strip().startswith(HEAD) for l in lines)
        if had_include:
            write_lines(cfg, strip_managed(lines))
        had_file = os.path.exists(bpath)
        if had_file:
            os.remove(bpath)
        if had_include or had_file:
            print("Removed keybinds from", cfg)
        else:
            print("No managed keybinds found in", cfg)
        return

    if mode != "paste":
        print("error: unknown mode %s" % mode, file=sys.stderr)
        sys.exit(1)

    block = sys.argv[2] if len(sys.argv) > 2 else ""
    if not block:
        print("error: no block given", file=sys.stderr)
        sys.exit(1)

    kept_from = preferred_exprs(cfg_binds, managed_binds)
    new_block, kept = rebuild_block(block, kept_from)

    # every state now lives in the managed file, so old lines in config.kdl go
    scrub = {i for i, b in cfg_binds if b["chillpill"] and b["state"] in STATE_SET}
    cleaned = [ln for i, ln in enumerate(lines) if i not in scrub]
    cleaned = strip_managed(cleaned)

    # the managed file itself, without the marker comments niri doesn't need
    write_lines(bpath, new_block)
    # the include goes last so it overrides niri's default binds
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    cleaned += ([""] if cleaned else []) + [HEAD, INCLUDE_LINE, TAIL]
    write_lines(cfg, cleaned)

    msg = ["Wrote %s and added an include to %s" % (bpath, cfg)]
    if kept:
        msg.append("Kept your existing combos for: " + ", ".join(kept))
    _, _, cb, mb = load(cfg)
    dups = report(cb, mb)["dup_combos"]
    msg.append("Duplicate combos remaining: " + (", ".join(sorted(dups)) if dups else "none"))
    print("\n".join(msg))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(1)
