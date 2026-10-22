#!/usr/bin/env python3
"""Export data/vendors.json to a flat Hugging Face dataset in hf-dataset/.

  python3 scripts/export_hf.py

Writes hf-dataset/vendor_fields.csv, hf-dataset/vendor_fields.jsonl and
hf-dataset/README.md (dataset card). One row per tool + field. Standard library only.
Set SITE_URL to put the real site link in the card.
"""
import csv, json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "hf-dataset"
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/") or "<SITE_URL>"
FIELD_ORDER = ["trains_by_default", "retention", "zdr", "abuse_monitoring",
               "residency", "certifications", "hipaa_baa", "self_host"]
COLUMNS = ["vendor_slug", "tool_name", "category", "vendor", "field", "field_label",
           "value", "status", "detail", "source_url", "quote", "checked_date"]


def rows(data):
    labels = data["field_labels"]
    for v in data["vendors"]:
        for k in FIELD_ORDER:
            x = v["fields"][k]
            yield {
                "vendor_slug": v["slug"], "tool_name": v["name"], "category": v["category"],
                "vendor": v["vendor"], "field": k, "field_label": labels[k],
                "value": "" if x["value"] == "unverified" else x["value"],
                "status": "unverified" if x["value"] == "unverified" else "verified",
                "detail": x.get("detail", ""), "source_url": x.get("source", ""),
                "quote": x.get("quote", ""), "checked_date": x.get("checked", ""),
            }


def card(data, rs):
    n_tools = len(data["vendors"])
    n_unver = sum(r["status"] == "unverified" for r in rs)
    checked = max(r["checked_date"] for r in rs)
    fields = "\n".join(f"| `{k}` | {data['field_labels'][k]} |" for k in FIELD_ORDER)
    return f"""---
license: cc-by-4.0
language:
- en
pretty_name: "Where Do My Prompts Go? AI tool data policies"
size_categories:
- n<1K
task_categories:
- table-question-answering
tags:
- privacy
- data-retention
- ai-policy
- llm
- compliance
configs:
- config_name: default
  data_files:
  - split: train
    path: vendor_fields.csv
---

# Where Do My Prompts Go? AI tool data policies

How {n_tools} AI tools (model APIs, coding tools, inference hosts, observability tools) handle user data:
whether they train on it by default, how long they keep it, zero data retention (ZDR), abuse-monitoring
exceptions, data residency, SOC 2 / ISO 27001, HIPAA BAA and self-host options.

Each row is one tool and one field. Each verified value comes with the URL of the vendor's own page,
a quote from that page and the date it was checked.

- Site: {SITE_URL}
- Last full check: {checked}
- Rows: {len(rs)} ({n_tools} tools x {len(FIELD_ORDER)} fields)
- Unverified rows: {n_unver}

## Files

- `vendor_fields.csv`: one row per tool + field
- `vendor_fields.jsonl`: same rows, one JSON object per line

## Columns

| Column | Meaning |
|---|---|
| `vendor_slug` | Short id of the tool, same as the URL on the site |
| `tool_name` | Tool name |
| `category` | Model APIs, Coding tools, etc. |
| `vendor` | Company behind the tool |
| `field` | Field id (see below) |
| `field_label` | Field name in plain English |
| `value` | Short answer. Empty when `status` is `unverified` |
| `status` | `verified` (an official page supports the value) or `unverified` |
| `detail` | Longer note: plan differences, limits, or why it is unverified |
| `source_url` | Official vendor page used (for unverified rows: the page that was checked) |
| `quote` | Exact text from `source_url` that supports `value`. Empty for unverified rows |
| `checked_date` | Date the source was read (YYYY-MM-DD) |

Fields:

| `field` | Label |
|---|---|
{fields}

## How the data is made

Only vendor pages are used: privacy policies, terms, DPAs, trust and security pages, docs and company blogs.
A value is marked verified only when a quote on such a page supports it. If no official page states it
clearly, the row is `unverified` and `detail` says what was checked. Missing values are not filled in from
other sites.

Policies often differ by plan (free, paid, enterprise); `detail` notes this. A signed contract or DPA
overrides any public page. This is not legal advice.

## How it is updated

`data/vendors.json` in the site repo is the source of truth. A nightly script fetches every source page and
diffs it against the last snapshot. A diff means the page is re-read by hand; the data changes only after that.
These files are regenerated with `python3 scripts/export_hf.py`.

## License

Data and descriptions: CC BY 4.0. The `quote` column contains short excerpts from vendor pages, included
to show the source of each value; those excerpts remain the property of their owners.
"""


def main():
    data = json.loads((ROOT / "data" / "vendors.json").read_text())
    rs = list(rows(data))
    OUT.mkdir(exist_ok=True)
    with open(OUT / "vendor_fields.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rs)
    with open(OUT / "vendor_fields.jsonl", "w", encoding="utf-8") as fh:
        for r in rs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "README.md").write_text(card(data, rs), encoding="utf-8")
    print(f"Wrote {len(rs)} rows to {OUT.relative_to(ROOT)}/ ({sum(r['status'] == 'unverified' for r in rs)} unverified)")


if __name__ == "__main__":
    main()
