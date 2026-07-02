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
`platform` MCP server and rendering the result directly in the chat. Three
tools do everything you need: `cube_list` discovers the available datasets,
`cube_describe` lists a dataset's fields, and `cube_query` runs the query and
returns rows.

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

`cube_describe` returns only a single cube's own fields — it does **not**
expose how cubes join to each other, or which paths exist between two cubes.
Cube's own query engine has a way to pin an ambiguous path (`joinHints`), but
`cube_query` doesn't accept it — only the fields listed in Step 3 go through.
So when more than one path connects two cubes, Cube.js picks one on its own,
and the answer can silently change depending on which one it picks.

When a question spans more than one cube and the relationship between them
isn't obviously singular from their names and descriptions — two plausible
routes to the same field, or a fact table that could relate to a dimension
both directly and through a third cube — **don't guess**. State the ambiguity
plainly and ask the user to confirm the intended relationship or grain — e.g.
"revenue per order item" vs. "revenue per user" — before running the query.
Prefer the simplest single-cube answer whenever the question doesn't actually
require crossing cubes at all.

## Step 3: Build the query

`cube_query` takes the pieces of a Cube.js query directly as tool arguments —
no query string, no shell quoting, just pass the object. Getting the shape of
each field exactly right avoids most tool errors:

| Field | Shape | Notes |
|---|---|---|
| `measures` | `string[]` | quantities to aggregate, e.g. `gold_order_items_enriched.count` |
| `dimensions` | `string[]` | attributes to group/break down by |
| `segments` | `string[]` | named filters from `cube_describe`, layered on top like an extra filter |
| `timeDimensions` | `[{ dimension, granularity?, dateRange? }]` | see below |
| `filters` | `[{ member, operator, values }]` or `[{ member, operator }]` | two distinct shapes, see below |
| `order` | `[[member, "asc" \| "desc"], …]` | **only the array-of-tuples form** — Cube's own API also accepts an object map elsewhere, but this tool doesn't; use `[["gold_order_items_enriched.count", "desc"]]`, not `{"gold_order_items_enriched.count": "desc"}` |
| `limit` | `number`, max 1000 | default 100 if omitted |
| `offset` | `number` | for paging past `limit` |
| `timezone` | IANA string, e.g. `Europe/Amsterdam` | defaults to UTC |

**`timeDimensions[].granularity`** — one of `day`, `week`, `month`, `quarter`,
`year`. Omit it entirely for a single total across the whole range instead of
a series.

**`timeDimensions[].dateRange`** — a relative string (`"last quarter"`, `"last
12 months"`, `"this month"`) or an explicit `["2026-01-01", "2026-03-31"]`
pair of ISO dates.

**`filters`** has two shapes, and mixing up their fields is the easiest way to
get a syntax error:
- Binary: `{ "member": "...", "operator": "...", "values": ["..."] }` —
  `values` is **always an array of strings**, even for numbers or dates
  (`["100"]`, not `[100]`). Valid operators: `equals`, `notEquals`, `contains`,
  `notContains`, `startsWith`, `notStartsWith`, `endsWith`, `notEndsWith`,
  `gt`, `gte`, `lt`, `lte`, `inDateRange`, `notInDateRange`, `beforeDate`,
  `beforeOrOnDate`, `afterDate`, `afterOrOnDate`.
- Unary: `{ "member": "...", "operator": "set" | "notSet" }` — no `values`
  field at all for these two.
- Every filter in the array is **AND**-combined. Cube's own query language
  supports nested `{"or": [...]}` / `{"and": [...]}` filter groups, but this
  tool's schema only accepts the flat list above — those nested shapes aren't
  available here. If a question genuinely needs OR logic across filters, say
  that's not expressible here rather than forcing an AND that changes the
  meaning.

Examples:

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

Filtered:

```json
{
  "measures": ["gold_order_items_enriched.revenue"],
  "dimensions": ["gold_order_items_enriched.traffic_source"],
  "filters": [
    { "member": "gold_order_items_enriched.is_refunded", "operator": "equals", "values": ["false"] }
  ]
}
```

Rules of thumb:

- One measure + one dimension → chart candidate by category.
- One measure + one `timeDimensions` with `granularity` → chart candidate over time.
- Multiple measures or multiple dimensions → table only; don't try to chart it.
- Always set `limit` explicitly for "top N" questions (`limit: N` + matching
  `order`). Default is 100 rows, hard max 1000 — don't rely on the default for
  an open-ended pull.

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

### 5a. Table — always

Render every returned row as a standard Markdown table, not ASCII art — it
renders natively in the chat UI and needs no manual column-width math.
Right-align numeric columns with the `---:` header-separator syntax. Format
numbers with thousands separators; round to 2 decimals when not integral.

```markdown
| traffic_source | count |
|---|---:|
| Search | 142,318 |
| Organic | 88,204 |
| Email | 41,907 |
| Facebook | 22,015 |
| Display | 9,471 |
```

### 5b. Chart — when the shape allows

If the query returned exactly one measure plus exactly one dimension
(categorical or time), also create an **artifact** with a real chart (bar
chart for a category breakdown, line or bar chart for a time series) so it
renders inline as an actual chart, not text art. A small self-contained SVG is
usually the simplest and most portable choice — no external libraries or
network access needed — but use whatever chart artifact fits the client best.
Label the axes/categories and show the values; keep the color scheme simple.

If the current client doesn't support artifacts, skip the chart and rely on
the table alone — don't fall back to drawing a chart out of text characters.

Skip the chart entirely when: the result set is empty, the query has 2+
measures, 2+ dimensions, a single scalar value (no dimension), or all measure
values are zero or null. For a single scalar answer, state the number in prose
followed by the one-row table — no chart.

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
  YAML.
- If `cube_list` returns no cubes, tell the user their organization doesn't
  appear to have a semantic model set up yet — don't guess why.
