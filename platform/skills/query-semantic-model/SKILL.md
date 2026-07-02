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

## Step 2: Known limitation — join relationships aren't exposed by cube_describe

`cube_describe` returns only a single cube's own fields — it does **not**
expose how cubes join to each other, or which paths exist between two cubes.
So when more than one path connects two cubes, you can't inspect the join
graph to see which one is right; Cube.js will otherwise pick one on its own,
and the answer can silently change depending on which one it picks.

You can still pin the path explicitly with `joinHints`: a list of join paths,
where each path is an ordered array of cube names to route through — two cubes
for a direct join, more for a multi-hop path, e.g.
`[["gold_order_items_enriched", "gold_users_with_order_stats"]]` or
`[["orders", "line_items", "products"]]`. But you're choosing that path blind
— you have a tool to express a path, not a way to discover which path is
correct.

So: only set `joinHints` when the path is genuinely obvious from the cube and
field names/descriptions. When a question spans more than one cube and you
can't point to an obviously singular relationship between them — two
plausible routes to the same field, or a fact table that could relate to a
dimension both directly and through a third cube — **don't guess**. State the
ambiguity plainly and ask the user to confirm the intended relationship or
grain — e.g. "revenue per order item" vs. "revenue per user" — before running
the query. Whenever you do set `joinHints`, say so in your explanation
afterward — which path you used and why — so the user can catch a wrong
assumption. Prefer the simplest single-cube answer whenever the question
doesn't actually require crossing cubes at all.

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
| `filters` | see below | leaf conditions, optionally nested in `and`/`or` groups |
| `order` | `[[member, dir], …]` or `{ member: dir }` | either shape works — array of `[member, "asc"\|"desc"]` pairs, or an object map |
| `joinHints` | `[[cube, …], …]` | pins an ambiguous join path — each entry is an ordered path of cube names (two or more), see Step 2 |
| `limit` | `number`, max 1000 | default 100 if omitted |
| `offset` | `number` | for paging past `limit` |
| `timezone` | IANA string, e.g. `Europe/Amsterdam` | defaults to UTC |
| `total` | `boolean` | also returns the total matching row count, ignoring `limit`/`offset` — useful for "(showing 10 of 842)" |
| `ungrouped` | `boolean` | returns raw rows without aggregating by the dimensions, for inspecting individual records rather than summarizing — the row limit still applies |

**`timeDimensions[].granularity`** — one of `day`, `week`, `month`, `quarter`,
`year`. Omit it entirely for a single total across the whole range instead of
a series.

**`timeDimensions[].dateRange`** — a relative string (`"last quarter"`, `"last
12 months"`, `"this month"`) or an explicit `["2026-01-01", "2026-03-31"]`
pair of ISO dates.

**`timeDimensions[].compareDateRange`** — for period-over-period questions
("this month vs. last month"), an array of two or more ranges (each a relative
string or `[from, to]` pair) to compare the same measure across.

**`filters`** is a list of conditions, each one of:
- A condition: `{ "member": "...", "operator": "...", "values": [...] }`.
  Values are usually strings (`["100"]` works fine even for numbers/dates),
  but numbers, booleans, and `null` are accepted too. Operators: `equals`,
  `notEquals`, `in`, `notIn`, `contains`, `notContains`, `startsWith`,
  `notStartsWith`, `endsWith`, `notEndsWith`, `gt`, `gte`, `lt`, `lte`,
  `inDateRange`, `notInDateRange`, `onTheDate`, `beforeDate`, `beforeOrOnDate`,
  `afterDate`, `afterOrOnDate`, `measureFilter`. `set` / `notSet` check
  presence and take **no** `values`.
- A group: `{ "and": [...] }` or `{ "or": [...] }`, where each entry is again
  a condition or a group (they can nest). Top-level entries in the `filters`
  array are implicitly AND-combined; reach for an explicit `or` group the
  moment a question needs "either of these" rather than "all of these" —
  mixing dimension and measure conditions inside the same `and`/`or` group
  isn't supported, keep those separate.

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

Filtered with OR logic ("either refunded or a test order"):

```json
{
  "measures": ["gold_order_items_enriched.count"],
  "filters": [
    {
      "or": [
        { "member": "gold_order_items_enriched.is_refunded", "operator": "equals", "values": ["true"] },
        { "member": "gold_order_items_enriched.is_test_order", "operator": "equals", "values": ["true"] }
      ]
    }
  ]
}
```

Crossing cubes with a pinned join path (see Step 2):

```json
{
  "measures": ["gold_order_items_enriched.revenue"],
  "dimensions": ["gold_users_with_order_stats.country"],
  "joinHints": [["gold_order_items_enriched", "gold_users_with_order_stats"]]
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
