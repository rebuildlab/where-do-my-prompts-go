"""Derived values shared by build.py and make_graphics.py (stdlib only).

Everything here is computed from data/vendors.json at build time. The rules that turn a
field value into a status (ok / mid / bad / unk / na) are spelled out below and on the
Method page, so a reader can check every colour on the site against the raw value.
"""
import json, math, re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
FIELD_ORDER = ["trains_by_default", "retention", "zdr", "abuse_monitoring",
               "residency", "certifications", "hipaa_baa", "self_host"]
SHORT = {"trains_by_default": "Trains", "retention": "Retention", "zdr": "ZDR",
         "abuse_monitoring": "Abuse mon.", "residency": "SG/APAC", "certifications": "SOC2/ISO",
         "hipaa_baa": "HIPAA BAA", "self_host": "Self-host"}
REGION_LABEL = {"sg": "Singapore option", "apac": "APAC, not Singapore",
                "none": "No APAC option", "unverified": "Unverified"}
TONES = ["ok", "mid", "bad", "unk", "na"]
TONE_LABEL = {"ok": "Favourable", "mid": "Caution", "bad": "Unfavourable",
              "unk": "Unverified", "na": "Neutral / n/a"}
TONE_GLYPH = {"ok": "✓", "mid": "!", "bad": "×", "unk": "?", "na": "–"}
TONE_RANK = {"ok": 0, "mid": 1, "na": 2, "bad": 3, "unk": 4}

# Plain-English version of the rules, rendered on the Method page.
TONE_RULES = {
    "trains_by_default": "no → favourable · depends on plan/provider → caution · yes → unfavourable",
    "retention": "nothing kept by default → favourable · a range that starts at zero, or up to 30 days, or an unstated period → caution · more than 30 days or until deleted → unfavourable (caution if the value says it only applies conditionally, e.g. “if shared”) · configurable / follows other settings → neutral",
    "zdr": "available (default, self-serve, on request or on approval) → favourable · partial → caution · not offered → unfavourable · not applicable → neutral",
    "abuse_monitoring": "none stated → favourable · any carve-out that can keep or review content → caution · not applicable → neutral",
    "residency": "Singapore region → favourable · APAC but not Singapore → caution · no APAC option → neutral (this column is an APAC lens)",
    "certifications": "SOC 2 or ISO 27001 confirmed → favourable · other certifications only → caution",
    "hipaa_baa": "BAA available → favourable · not available → unfavourable",
    "self_host": "yes → favourable · partial or a separate product → caution · hosted only → neutral",
}


def load():
    data = json.loads((ROOT / "data" / "vendors.json").read_text())
    changelog = json.loads((ROOT / "data" / "changelog.json").read_text())["entries"]
    snaps_path = ROOT / "snapshots" / "index.json"
    snapshots = json.loads(snaps_path.read_text()) if snaps_path.exists() else {}
    return data, changelog, snapshots


def is_unverified(value):
    return value.strip().lower().startswith("unverified")


def trains_key(v):
    s = v.lower()
    for k in ("unverified", "depends", "yes", "no"):
        if s.startswith(k):
            return k
    return "depends"


def zdr_key(v):
    s = v.lower()
    if s.startswith("unverified"): return "unverified"
    if s.startswith("n/a"): return "n/a"
    if s.startswith("no"): return "not offered"
    if s.startswith("partial"): return "partial"
    return "available"


_UNIT = {"hour": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365}
_ZERO = ("none by default", "not logged", "transient", "deleted after output", "stateless")
_FOREVER = ("indefinite", "until deleted", "forever", "stored")
_UNSTATED = ("not specified", "not fixed", "unspecified", "limited period")


def retention(value):
    """Parse a retention value into {kind, lo, hi} in days (math.inf = until deleted).

    kind: 'unverified', 'range' (lo/hi known), 'unstated' (vendor gives no number),
    'config' (configurable / follows other settings).
    """
    s = value.lower()
    if is_unverified(s):
        return {"kind": "unverified", "lo": None, "hi": None}
    nums = [float(n) * _UNIT[u] for n, u in re.findall(r"(\d+(?:\.\d+)?)\s*(hour|day|week|month|year)s?", s) if float(n) > 0]
    zero = any(z in s for z in _ZERO) or bool(re.search(r"(?<![\d.])0\s*days?\b", s))
    forever = any(f in s for f in _FOREVER)
    if any(u in s for u in _UNSTATED) and not nums:
        return {"kind": "unstated", "lo": None, "hi": None}
    if not nums and not zero and not forever:
        return {"kind": "config", "lo": None, "hi": None}
    pts = list(nums)
    if zero: pts.append(0.0)
    if forever: pts.append(math.inf)
    return {"kind": "range", "lo": min(pts), "hi": max(pts)}


def fmt_days(d):
    if d is None: return "?"
    if d == math.inf: return "until deleted"
    if d == 0: return "0d"
    if d < 1: return f"{round(d * 24)}h"
    if d >= 365 and d % 365 == 0: return f"{int(d // 365)}y"
    return f"{int(d)}d"


def tone(field, value, vendor=None):
    s = value.strip().lower()
    if field == "residency" and vendor is not None:
        if is_unverified(s): return "unk"
        return {"sg": "ok", "apac": "mid", "none": "na", "unverified": "unk"}[vendor["region_filter"]]
    if is_unverified(s): return "unk"
    if field == "trains_by_default":
        return {"no": "ok", "yes": "bad"}.get(trains_key(value), "mid")
    if field == "zdr":
        return {"available": "ok", "not offered": "bad", "partial": "mid", "n/a": "na"}[zdr_key(value)]
    if field == "retention":
        r = retention(value)
        if r["kind"] == "config": return "na"
        if r["kind"] == "unstated": return "mid"
        if r["hi"] == 0: return "ok"
        if r["lo"] == 0 or r["lo"] <= 30: return "mid"
        if "(if " in s: return "mid"  # conditional, e.g. "1 year (if shared)"
        return "bad"
    if field == "abuse_monitoring":
        if s.startswith("n/a"): return "na"
        if s.startswith("none"): return "ok"
        return "mid"
    if field == "certifications":
        return "ok" if ("soc 2" in s or "iso 27001" in s) else "mid"
    if field == "hipaa_baa":
        if s.startswith("yes"): return "ok"
        if s.startswith("no"): return "bad"
        return "mid"
    if field == "self_host":
        if s.startswith("yes"): return "ok"
        if s.startswith("no"): return "na"
        return "mid"
    if field == "residency":
        return "na"
    return "na"


def domain(url):
    return urlparse(url).netloc.removeprefix("www.") if url else ""


def enrich(vendors):
    """Attach a tone to every field and a tone count to every vendor (in place)."""
    for v in vendors:
        counts = {t: 0 for t in TONES}
        for k in FIELD_ORDER:
            t = tone(k, v["fields"][k]["value"], v)
            v["fields"][k]["_tone"] = t
            counts[t] += 1
        v["_counts"] = counts
        v["_ret"] = retention(v["fields"]["retention"]["value"])
    return vendors


def stats(vendors, snapshots=None):
    n = len(vendors)
    tk = [trains_key(v["fields"]["trains_by_default"]["value"]) for v in vendors]
    rets = [(v, v["_ret"]) for v in vendors if v["_ret"]["kind"] == "range"]
    zero = [v["name"] for v, r in rets if r["hi"] == 0]
    longest_lo = max((r["lo"] for _, r in rets), default=None)
    longest = [v["name"] for v, r in rets if r["lo"] == longest_lo]
    finite_his = [r["hi"] for _, r in rets if r["hi"] != math.inf]
    total_fields = n * len(FIELD_ORDER)
    unver = sum(1 for v in vendors for k in FIELD_ORDER if is_unverified(v["fields"][k]["value"]))
    sources = sorted({v["fields"][k]["source"] for v in vendors for k in FIELD_ORDER if v["fields"][k]["source"]})
    zdr = [zdr_key(v["fields"]["zdr"]["value"]) for v in vendors]
    checked = max(x["checked"] for v in vendors for x in v["fields"].values())
    baseline = min(x["checked"] for v in vendors for x in v["fields"].values())
    snaps = snapshots or {}
    return {
        "n": n, "checked": checked, "baseline": baseline, "total_fields": total_fields, "unverified": unver,
        "trains_yes": tk.count("yes"), "trains_no": tk.count("no"),
        "trains_depends": tk.count("depends"), "trains_unverified": tk.count("unverified"),
        "trains_depends_names": [v["name"] for v, k in zip(vendors, tk) if k == "depends"],
        "zero_retention": zero, "longest_retention_lo": longest_lo, "longest_retention": longest,
        "max_finite_days": max(finite_his) if finite_his else None,
        "zdr_available": zdr.count("available"), "zdr_applicable": n - zdr.count("n/a"),
        "sources": len(sources), "source_domains": len({domain(u) for u in sources}),
        "monitored_pages": len(snaps),
        "monitor_errors": sum(1 for x in snaps.values() if x.get("last_error")),
        "monitor_last": max((max(x.get("last_checked") or "", x.get("last_attempt") or "") for x in snaps.values()), default=""),
        "sg_region": sum(1 for v in vendors if v["region_filter"] == "sg"),
        "apac_region": sum(1 for v in vendors if v["region_filter"] in ("sg", "apac")),
    }


# ---------- source checks and the event stream (all from files on disk) ----------

def _snap_status(x):
    """(date, ok) for one index.json entry: an error counts if it is at least as new as the last good fetch."""
    good, bad = x.get("last_checked") or "", x.get("last_attempt") or ""
    if x.get("last_error") and bad >= good:
        return bad, False
    return good, True


def source_map(vendors, snapshots):
    """url -> sorted vendor slugs, from the fields that cite it plus the checker's own index."""
    m = {}
    for v in vendors:
        for k in FIELD_ORDER:
            u = v["fields"][k]["source"]
            if u:
                m.setdefault(u, set()).add(v["slug"])
    for u, x in (snapshots or {}).items():
        m.setdefault(u, set()).update(x.get("vendors") or [])
    return {u: sorted(s) for u, s in m.items()}


def index_versions(snapshots):
    """Working copy of snapshots/index.json, then each earlier commit of that file.

    Commit order is not check order. A later commit can restore an older index, so "latest"
    is decided by the dates stored in the entries, not by which commit is newest.
    CI checks this file out with fetch-depth: 0 so every real run is reachable."""
    import subprocess
    versions = [snapshots or {}]
    try:
        revs = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%H", "--", "snapshots/index.json"],
                              capture_output=True, text=True, timeout=20, check=True).stdout.split()
        for h in revs[:400]:
            raw = subprocess.run(["git", "-C", str(ROOT), "show", f"{h}:snapshots/index.json"],
                                 capture_output=True, text=True, timeout=20)
            if raw.returncode == 0 and raw.stdout.strip():
                versions.append(json.loads(raw.stdout))
    except Exception:
        pass
    return versions


def history_from(versions):
    """Every (run date, url) -> (ok, error) present in any stored index. Nothing is interpolated."""
    res = {}
    for ver in versions:
        for u, x in (ver or {}).items():
            d, ok = _snap_status(x)
            if d:
                res.setdefault((d, u), (ok, x.get("last_error")))
    return res  # {(date, url): (ok, error)}


def check_history(snapshots):
    """Every (run date, url) -> ok/error result we can actually prove.

    snapshots/index.json only keeps the latest result per URL, so older runs are read back from
    earlier git commits of that file when the repo has them (CI: checkout with fetch-depth: 0).
    Nothing is interpolated: a date with no stored result has no cell."""
    return history_from(index_versions(snapshots))


def newest_entries(versions):
    """Per URL, the index entry whose status date is the latest.

    Ties keep the earlier version in `versions` (working tree, then newer commits). A newer
    commit that restored an older index does not hide a later check date."""
    best, best_d = {}, {}
    for ver in versions:
        for u, x in (ver or {}).items():
            d, _ok = _snap_status(x)
            if d and (u not in best_d or d > best_d[u]):
                best[u] = x
                best_d[u] = d
    return best


def latest_run(history):
    """The newest checker run by date. Only URLs stamped with that date are counted."""
    if not history:
        return None
    date = max(d for d, _u in history)
    res = [r for (d, _u), r in history.items() if d == date]
    errors = sum(1 for ok, _err in res if not ok)
    return {"date": date, "sources": len(res), "errors": errors, "ok": len(res) - errors}


def apply_latest_run(st, history):
    """Point the monitor totals at the newest checker run. Field dates on `st` stay as they are.

    `full_check` is the one date the status bar, data version, llms.txt and changelog share.
    It is a date read from a checker result, or the newest field-checked date when no run exists."""
    run = latest_run(history)
    if run:
        st["monitored_pages"] = run["sources"]
        st["monitor_errors"] = run["errors"]
        st["monitor_last"] = run["date"]
        st["full_check"] = run["date"]
    else:
        st["full_check"] = st.get("monitor_last") or st.get("checked") or ""
    return st


def uptime(vendors, snapshots, history):
    """Per vendor, per run date: how many of its monitored sources fetched OK."""
    smap = source_map(vendors, snapshots)
    dates = sorted({d for d, _ in history})
    rows = []
    for v in vendors:
        urls = [u for u, s in smap.items() if v["slug"] in s and u in (snapshots or {})]
        cells = []
        for d in dates:
            got = [history[(d, u)] for u in urls if (d, u) in history]
            if not got:
                cells.append({"date": d, "state": "none", "ok": 0, "n": 0, "errors": []})
                continue
            ok = sum(1 for g in got if g[0])
            errs = [(u, history[(d, u)][1]) for u in urls if (d, u) in history and not history[(d, u)][0]]
            state = "ok" if ok == len(got) else ("bad" if ok == 0 else "mid")
            cells.append({"date": d, "state": state, "ok": ok, "n": len(got), "errors": errs})
        cited = {v["fields"][k]["source"] for k in FIELD_ORDER if v["fields"][k]["source"]}
        rows.append({"slug": v["slug"], "name": v["name"], "urls": urls, "cells": cells,
                     "unmonitored": sorted(cited - set(snapshots or {}))})
    return dates, rows


def events(vendors, changelog, snapshots, history, labels):
    """The policy event stream. Every line is derived from a file in the repo:
    changelog.json entries, checker results in snapshots/index.json (and its git history),
    fields re-checked after the baseline, unverified fields, and the baseline itself."""
    ev = []
    by_slug = {v["slug"]: v for v in vendors}
    st = stats(vendors, snapshots)
    smap = source_map(vendors, snapshots)
    for x in changelog or []:
        ev.append({"date": x["date"], "sev": "CHANGE", "vendor": x.get("slug", ""), "field": x.get("field", ""),
                   "msg": x.get("summary", ""), "src": x.get("source", "")})
    for d in sorted({d for d, _ in history}):
        res = {u: r for (dd, u), r in history.items() if dd == d}
        ok = sum(1 for r in res.values() if r[0])
        ev.append({"date": d, "sev": "INFO", "vendor": "checker", "field": "run",
                   "msg": f"{len(res)} sources fetched and diffed: {ok} ok, {len(res) - ok} failed", "src": ""})
        for u, (good, err) in sorted(res.items()):
            if not good:
                who = smap.get(u, [])
                ev.append({"date": d, "sev": "ERROR", "vendor": ",".join(who) or "checker",
                           "field": "fetch", "src": u,
                           "msg": f"{err}; previous snapshot kept" + ("" if who else " (no current field cites this URL)")})
    for v in vendors:
        for k in FIELD_ORDER:
            f = v["fields"][k]
            if f["checked"] > st["baseline"]:
                ev.append({"date": f["checked"], "sev": "INFO", "vendor": v["slug"], "field": k,
                           "msg": f'field re-checked against source: "{f["value"]}"', "src": f["source"]})
            if is_unverified(f["value"]):
                ev.append({"date": f["checked"], "sev": "WARN", "vendor": v["slug"], "field": k,
                           "msg": "unverified: no official page stated this clearly", "src": f["source"]})
    ev.append({"date": st["baseline"], "sev": "INFO", "vendor": "dataset", "field": "baseline",
               "msg": f'baseline recorded: {st["n"]} tools, {st["total_fields"]} fields, {st["sources"]} cited pages',
               "src": ""})
    rank = {"CHANGE": 0, "ERROR": 1, "WARN": 2, "INFO": 3}
    base_last = lambda e: 1 if e["field"] == "baseline" else 0
    ev.sort(key=lambda e: (e["date"], -base_last(e), -rank[e["sev"]]), reverse=True)
    return ev


if __name__ == "__main__":
    data, _, snaps = load()
    vs = enrich(data["vendors"])
    for v in vs:
        print(f'{v["slug"]:16} ' + " ".join(f'{SHORT[k][:6]}={v["fields"][k]["_tone"]:3}' for k in FIELD_ORDER),
              "| ret", v["_ret"]["kind"], fmt_days(v["_ret"]["lo"]), fmt_days(v["_ret"]["hi"]))
    print(json.dumps(stats(vs, snaps), indent=1, default=str))
