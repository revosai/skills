---
name: metrics
description: >
  Find and explore RevOS metrics — the measures of the org's semantic model,
  as the app's Metrics page lists them — through the RevOS MCP server: which
  metrics exist, what each one aggregates and how it's formatted, which
  tables, segments, and dashboard cards use it, and what its value is right
  now, counted over a segment or a few conditions and optionally broken down
  by a dimension. Use this whenever the user asks "what metrics do we have",
  "is there a metric for win rate / ARR / open pipeline", "where is this
  metric used", "what's open pipeline for the EMEA segment", "deal amount by
  stage", or wants a metric's value the same way a dashboard card would show
  it — even if they never say "metric". For putting a metric on a dashboard,
  use the dashboards skill; it builds on this one.
---

# Metrics

A **metric** is a measure of the semantic model, fully qualified:
`crm_deals.amount`. The app's **Metrics** page lists every measure of the
cubes built from data sources, and a metric's own page lets you count it over
a **scope** (a segment, or a few conditions) and **break it down** by a
dimension — the same three settings a dashboard card stores. This skill reads
only; nothing here writes.

For ad-hoc analytical questions that aren't about one metric — several
measures at once, custom grouping, top-N across cubes — the
semantic-model skill is the better fit. Use this one when the user
thinks in terms of a named metric, or wants the number a card shows.

## The catalogue

```json
api_read { "resource": "cubes", "method": "meta", "params": { "fields": "name,title,description,type", "pageSize": 100 } }
api_read { "resource": "cubes", "method": "meta", "params": { "filter": "name == \"crm_deals\"" } }
```

The app lists measures of **source cubes only**. Leave out:

- `type: "view"` — a table's view (`model_…`) re-exports measures under new
  names; each such measure's `aliasMember` points at the original;
- generated cubes, marked `meta.abConnectionId: "revos"` — segment
  snapshots (`segment_…`) and tables' own columns (`model_stream_…`).
  `meta` can't be projected with `fields`; it's on the full record you read
  for a candidate cube anyway.

Per measure, what the catalogue shows:

| Column | From `meta` |
|---|---|
| Metric | `title` (`description` as its tooltip), `name` as the ref |
| Cube | the cube's `title` |
| Agg | `aggType`: `count`, `countDistinct`, `sum`, `avg`, `min`, `max`, `number`, … |
| Format | `format` `currency` / `percent`, else by type: Number, Text, Boolean, Date |

Only `type: "number"` measures can be counted on a card; say so if the user
picks a text, boolean, or time one.

When the user asks for a metric by meaning ("win rate", "ARR"), search titles
and descriptions. If nothing matches, say so and offer the closest, or adding
one with the cubes skill — never approximate silently with a different
measure.

### Where a metric is used

- **Tables**: a view `model_<table id, '-' → '_'>` re-exports the measure
  (`aliasMember == "<measure>"`). Map the id back with
  `api_read { "resource": "tables", "params": { "fields": "id,name" } }`.
- **Segments**: the measure (or a view alias of it) is a `member` in the
  segment's `filter`.
- **Dashboards**: `api_read { "resource": "dashboard-cards", "params": { "filter": "measure == \"<measure>\"" } }`.

## A metric's value

`api_read { "resource": "cubes", "method": "query", "body": { "query": … } }`,
built exactly as the app builds it — otherwise your number differs from the
one on the user's screen:

```json
{
  "measures": ["<measure>"],
  "filters": [ <the scope's conditions, as Cube filters> ],
  "joinHints": [ <each join path, split on "."> ]
}
```

Leave out `filters` / `joinHints` when empty.

### Scope

- **Every row** — no filters.
- **Conditions** — written in segment filter syntax (see the segments
  skill's `references/filter-syntax.md`) and translated with its table:
  `EQUAL` → `equals`, `EMPTY` → `notSet`, `CHECKED` → `equals "true"`, …
  Top-level `AND` items are separate `filters` entries; an `OR` becomes
  `{ "or": [ … ] }`, an `AND` group `{ "and": [ … ] }`. Skip conditions with no
  `member`, or no `value` where the operator needs one — the app does too.
  Check stored values with a cubes query before an `EQUAL` on a string.
- **A dynamic segment** — read it; translate *its* `filter` the same way, and
  put its `cubes[1..].joinPath` into `joinHints` first.
- **A static segment** — one filter instead of its conditions:
  `{ "member": "segment_<segment id, '-' → '_'>.id", "operator": "set" }`.
  It needs that `segment_…` cube in `meta`.

A segment fits a metric only when its **root cube is the metric's cube**
(`segment.cubes[0].joinPath`). A segment of companies can't scope a deal
metric — say so, and offer conditions on the company fields instead.

### Joins to other cubes

A condition or breakdown on another cube reads it along a **join path** from
the metric's cube: `crm_deals.crm_companies`. Check each hop against `joins`
in `meta` (declared on either side). When two routes exist, the choice
changes the number — ask which the user means. Send each path as a join
hint, `["crm_deals", "crm_companies"]`; the metric's own cube needs none.

Two conditions the app refuses, and you should too:

- **A condition on a measure** (`crm_deals.count > 3`). On a total it isn't
  per-row; it's not a scope.
- **A condition on a cube the metric's rows have many of** (`hasMany` /
  `one_to_many` along the path): each row is checked once per related row.

### Breakdown

The same query plus the dimension:

- not a time dimension: `"dimensions": ["<dim>"]`,
  `"order": { "<measure>": "desc", "<dim>": "asc" }` — largest groups first.
- a time dimension: `"timeDimensions": [{ "dimension": "<dim>", "granularity": "month" }]`,
  `"order": { "<dim>": "desc" }` — latest months first.

The groups add up to the total only for a `count` or `sum` measure whose
breakdown doesn't go along a join the rows have many of. Otherwise don't
present shares or an "Other" bucket, and for a fanned-out breakdown, say a
record linked to several groups is counted in each. A card shows the top 5
plus "Other"; the metric page shows 50.

### Reading the answer

- **No rows**: a count, count distinct, or sum is `0`; an average or other
  measure has no value — say "no value", not `0`.
- Format with the measure's `format` (currency, percent).
- Always say what the number is counted over: "€1.2M open pipeline, deals
  in the EMEA segment".
- `metadata.lastRefreshTime` on the result says how fresh it is; mention it
  when it's old or `slowQuery` is set.

Render a single value as one line, a breakdown as a small table, or a chart
when it helps.
