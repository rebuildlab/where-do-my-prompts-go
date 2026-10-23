# Ops console restyle (local branch `redesign-ops`, built on `redesign`)

Not pushed or deployed. Review with `git diff redesign..redesign-ops` or
`research/redesign/redesign-ops.patch`.

## What changed
- **Look**: dark-first monitoring console (light theme kept, toggle saved locally), dense
  12-column panel grid, monospace labels, status LEDs whose shape carries the meaning
  (circle ok, triangle caution, square unfavourable, ring unverified, dash n/a). No third-party branding.
- **Top bar + status line** on every page: wordmark, nav, theme toggle, a check pill
  ("108 sources checked · 3 fetch errors", links to the source checks), last check date,
  data version `v<generated>` and the first 8 hex chars of sha256(vendors.json), downloads.
- **Home**: six stat panels, the heatmap, retention and field-split panels, the **Policy event
  stream** (syslog-style, INFO/WARN/ERROR/CHANGE filter; 32 real events: 1 field re-check,
  3 fetch errors from the snapshot index, 26 unverified fields, the checker summary and the
  baseline), **source checks** per tool (one cell per checker run on record; currently one,
  "history starts 2026-10-21"), the compare table and data endpoints.
- **Compare table**: query bar (`vendor:openai trains:no`, `cat:coding`, `zdr:not-offered`,
  `region:none`, `baa:yes`, free words), shows how the query was parsed and lists ignored terms;
  facets and the query bar stay in sync; old URL params still work.
- **Tool pages**: service header (worst status sets the accent, fields tally, sources cited,
  source monitor result, last check), 8 field panels, the **evidence log** (one entry per field
  with date, OK/WARN/FAIL/UNVERIF/N/A tag, value, detail, quote, source, copy citation) and a
  source-check panel per cited URL (OK / ERROR / NOT IDX).
- **Changelog**: confirmed changes panel (still 0), the full event stream and source checks.
- **Share images and icons** redrawn in the console style from the same data.
- Checks: 29 pages, links, axe (light + dark) and 390px overflow all clean; query, legacy
  params, facet sync, theme persistence and severity filter tests added to `check_site.py`.

## Data changes (each backed by the stored source quote / a re-read of the source)
- `cohere.region_filter`: unverified → none (quote: "We do not use servers outside of the US").
- `windsurf.region_filter`: unverified → none (US core cluster + Frankfurt; no APAC region).
  The stored quote names only Frankfurt; the US part was confirmed by re-reading the cited blog.
- `github-copilot.fields.abuse_monitoring.value`: "provider ZDR; Claude Fable retained" →
  "provider ZDR, except Claude Fable 5 / 5.1 (Anthropic retains)"; `checked` 2026-10-23. The
  quote was re-read word for word on docs.github.com (model hosting).

# Redesign: UI and data graphics (local branch `redesign`)

Not pushed or deployed. Review with `git diff main..redesign` or `research/redesign/redesign.patch`.

## What changed
- **Home hero**: one-line value statement, CTAs, and a terminal card showing a real `jq` query
  against `data.json` (first tool in the data) with its real output.
- **Live stat strip** computed at build time: 12/25 don't train by default (10 depend on plan,
  3 unverified, 0 say yes outright), 15/21 offer ZDR (4 observability tools excluded),
  retention range 0d → until deleted (6 keep nothing; Together AI and Langfuse keep until
  deleted), 26/200 fields unverified. Each card links to the matching filtered view.
- **Compare table**: status chips on every column (favourable / caution / unfavourable /
  unverified / neutral), each with a glyph so colour isn't the only signal. Adds the
  abuse-monitoring column, a sticky header, sortable columns (aria-sort), a HIPAA BAA toggle,
  reset, a "/" search shortcut and an empty state. Old URL params (`q`, `cat`, `trains`,
  `zdr`, `region`) still work. Below 1060px the table turns into cards (no sideways scrolling).
- **Inline SVG charts from vendors.json**: fig. 1 status heatmap (25 tools × 8 fields, cells
  link to the evidence), fig. 2 default-retention ranges on a log scale (tools with no number
  are listed under it with their exact wording), fig. 3 split of tools per field.
- **Tool pages**: scorecard (8 tiles + tally + strip), notes shown as a callout, quotes shown
  as cited evidence (domain, path, checked date, "Copy citation"), a retention strip placing the
  tool among all others, a sticky "On this page" list, previous/next links.
- **Changelog**: a timeline. With no confirmed changes yet it shows the real baseline
  (2026-10-21) and the latest nightly check (108 pages, 3 fetch errors, 0 diff reports).
- **Method page**: new "How colours are assigned" section listing the exact rules and how retention is parsed.
- **Favicon** (SVG, aware of light and dark mode, plus ICO and apple-touch) and **OG cards** (1200x630): `og.png` for the
  site and `og/<slug>.png` per tool, drawn by `scripts/make_graphics.py` from the same data.
- **Design system**: one type scale and spacing scale (CSS variables), light and dark themes,
  self-hosted IBM Plex Mono subset (25 KB, OFL) for data and labels, system sans for text.
  No frameworks. CSS is 23 KB, JS is 3 KB, home HTML is 17 KB gzipped.

## New or changed files
- `scripts/derive.py` (new): tone rules, retention parsing, headline stats. `python3 scripts/derive.py` prints them.
- `scripts/build.py`: rewritten templates and SVG charts. Still stdlib-only for the HTML.
- `scripts/make_graphics.py` (new) + `scripts/fonts/`: PNG cards/icons (needs Pillow).
- `site/assets/style.css`, `app.js`, `fonts/`: new.
- `requirements.txt`: + pillow. `.gitignore`: + `public/` (the build output was tracked in this local copy, so it is now untracked).
- `research/redesign/`: screenshot, link-check and comparison scripts. The PNGs are excluded from git.

## Checks run
- All 29 pages render in headless Chrome (light and dark) with no console errors.
- 38 internal targets and every `#anchor` resolve. No horizontal overflow at 390px.
- axe-core (WCAG 2 A/AA plus best practice): 0 violations.
- External sources: 111 of 113 return 200. The 2 `openai.com` pages return 403 to scripts, which is a known issue.
