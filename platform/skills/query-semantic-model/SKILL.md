---
name: query-semantic-model
description: >
  Answer business questions about the org's RevOS data directly in chat by querying
  its live semantic model over MCP — "how many orders…", "revenue by…", "top N…",
  "trend over time…", "compare X to Y…" — or when explicitly asked to "query the
  semantic model", "run a cube query", "show me a chart", "plot…", "graph…".
  Discovers available datasets and fields with cube_list / cube_describe, runs the
  query with cube_query, and renders the result as a table and (when the shape
  fits) a bar chart, without leaving the chat.
---

# Query Semantic Model

Answer business questions by querying the org's live semantic model over the
`platform` MCP server and rendering the result directly in the chat — no BI tool,
no CLI, no local project. Three tools do everything you need: `cube_list`
discovers the available datasets, `cube_describe` lists a dataset's fields, and
`cube_query` runs the query and returns rows.

## Step 1: Discover what's queryable

Before guessing member names, call `cube_list` (optionally with a `search`
keyword) to see the cubes/views available to the org, each with a title,
description, and field counts.

Then call `cube_describe(name)` on the cube(s) the question needs. It returns
the exact `measures`, `dimensions` (with time granularities where relevant), and
`segments` you can reference — always addressed as `<CubeName>.<member>`, e.g.
`gold_order_items_enriched.count` or `gold_order_items_enriched.order_date`.

Never hardcode or guess a member name. If the question can't be answered from
what `cube_describe` returns, say so — don't invent a field.

## Step 2: Known limitation — join relationships are not exposed

`cube_describe` returns only a single cube's own fields. It does **not** expose
how cubes join to each other. This matters because Cube.js infers the join path
from the cubes that appear in a query, and when more than one path connects two
cubes, the answer changes depending on which one it picks — the single biggest
source of "the number looks wrong" bugs in a semantic-model query.

There is no local `cubes/*.yml` here to read a join graph from, and no way to
pin a join path with a dotted-prefix hint the way a developer working from the
RevOS CLI would. So when a question spans more than one cube and the
relationship between them isn't obviously singular from their names and
descriptions (for example, a fact table that could relate to a dimension both
directly and indirectly through a third cube), **don't guess**. State the
ambiguity plainly and ask the user to confirm the intended relationship or grain
— e.g. "revenue per order item" vs. "revenue per user" — before running the
query. Prefer the simplest single-cube answer whenever the question doesn't
actually require crossing cubes.

## Step 3: Build the query

`cube_query` takes the pieces of a Cube.js query directly as tool arguments —
no shell quoting, no temp files, just pass the object:

```json
{ "measures": ["gold_order_items_enriched.count"] }
```

```json
{
  "measures": ["gold_order_items_enriched.count"],
  "dimensions": ["gold_order_items_enriched.traffic_source"],
  "order": [["gold_order_items_enriched.count", "desc"]],
  "limit": 10
}
```

Time series (the chart-friendliest shape):

```json
{
  "measures": ["gold_order_items_enriched.revenue"],
  "timeDimensions": [
    {
      "dimension": "gold_order_items_enriched.order_date",
      "granularity": "month",
      "dateRange": "last 12 months"
    }
  ]
}
```

Rules of thumb:

- One measure + one dimension → bar chart by category.
- One measure + one `timeDimensions` with `granularity` → bar chart over time.
- Multiple measures or multiple dimensions → render as a table only; don't try
  to draw a chart.
- Always set `limit` explicitly for "top N" questions (`limit: N` + matching
  `order`). Default is 100 rows, hard max 1000 — don't rely on the default for
  an open-ended pull.
- `timeDimensions[].dateRange` accepts relative strings ("last quarter", "last
  7 days", "this month") or an explicit `[from, to]` pair of ISO dates.

## Step 4: Run the query

Call `cube_query` with the object you built. It returns
`{ rowCount, mayHaveMore, rows, resolvedQuery }`. `rows` is the array of results,
each row a flat object keyed by the same member names used in the query.
`mayHaveMore: true` means the row limit was hit — there may be more data, page
with `offset` if the user wants it — it does **not** mean rows were silently
dropped.

If the call errors, surface the message plainly. Common causes: a mistyped
member name (re-run `cube_describe`), or a `dateRange`/`granularity` used
against a dimension that isn't a time dimension.

## Step 5: Render the result in chat

Print **two** blocks in the reply, both as fenced code so they render
monospaced:

### 5a. ASCII table — always

Show every returned row. Right-align numeric columns, left-align everything
else. Format numbers with thousands separators; round to 2 decimals when not
integral. Truncate long string values to 32 chars with a trailing `…`.

```
traffic_source       count
─────────────────  ───────
Search             142,318
Organic             88,204
Email                41,907
Facebook             22,015
Display               9,471
```

### 5b. ASCII bar chart — when the shape allows

If the query returned exactly one measure plus exactly one dimension
(categorical or time), draw a horizontal bar chart underneath the table. Scale
bars to a width of **40 characters** based on the largest value in the result
set; use the `█` block character for filled cells.

```
Search        ████████████████████████████████████████  142,318
Organic       ████████████████████████▊                   88,204
Email         ███████████▊                                 41,907
Facebook      ██████▏                                      22,015
Display       ██▋                                           9,471
```

Skip the chart (table only) when: the result set is empty, the query has 2+
measures, 2+ dimensions, or a single scalar value (no dimension), or all
measure values are zero or null. For a single scalar answer, state the number
in prose followed by the one-line table — no chart.

## Step 6: Explain the result briefly

After the rendered output, add 1–3 short sentences in plain English: what was
measured, the highest/lowest bucket, and any obvious anomaly visible in the
table (e.g. a missing period, a single category dominating the total) — don't
speculate about causes not visible in the data. Suggest exactly **one** concrete
follow-up query the user could ask next.

## Rules

- Never hardcode cube or member names — always confirm via `cube_list` /
  `cube_describe` first.
- Never silently resolve an ambiguous multi-cube join — ask the user (see
  Step 2).
- Always render the table; render the chart only when the data shape supports
  it.
- Always set `limit` deliberately for "top N" questions; be aware of the
  default (100) and hard max (1000).
- This is a read-only, in-chat skill — no file writes, no local project, no
  YAML, no CLI commands. Don't reference `revos apply`, `revos cubes meta`,
  `cubes/*.yml`, or any local project state; none of that exists in this
  context.
- If `cube_list` returns no cubes, tell the user their organization doesn't
  appear to have a semantic model set up yet — don't guess why.
