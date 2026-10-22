---
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

How 25 AI tools (model APIs, coding tools, inference hosts, observability tools) handle user data:
whether they train on it by default, how long they keep it, zero data retention (ZDR), abuse-monitoring
exceptions, data residency, SOC 2 / ISO 27001, HIPAA BAA and self-host options.

Each row is one tool and one field. Each verified value comes with the URL of the vendor's own page,
a quote from that page and the date it was checked.

- Site: <SITE_URL>
- Last full check: 2026-10-21
- Rows: 200 (25 tools x 8 fields)
- Unverified rows: 26

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
| `trains_by_default` | Trains on your data by default |
| `retention` | Default retention |
| `zdr` | Zero data retention |
| `abuse_monitoring` | Abuse-monitoring exception |
| `residency` | Data residency / regions |
| `certifications` | SOC 2 / ISO 27001 |
| `hipaa_baa` | HIPAA BAA |
| `self_host` | Self-host option |

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
