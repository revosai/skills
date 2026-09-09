---
name: query-semantic-model
description: >
  Answer business questions about the org's RevOS data directly in chat by querying
  its live semantic model over MCP — "how many orders…", "revenue by…", "top N…",
  "trend over time…", "compare X to Y…" — and schema-discovery questions like
  "what's in my semantic model", "what can I query", "list cubes/datasets/fields",
  "describe a cube" — or when explicitly asked to "query the semantic model", "run
  a cube query", "show me a chart", "plot…", "graph…". Use this whenever you would
  otherwise call the RevOS api_read tool against the `cubes` resource directly —
  this skill is what turns its raw JSON into a rendered table, a chart when the
  shape fits, a safe choice of join path when a query spans multiple cubes, and a
  plain-English explanation, instead of a dumped tool result. This applies even
  when the question names a specific source system (HubSpot, Zammad, Exact
  Online, …) — answer aggregate/analytical questions from the semantic model,
  not a direct source connector.
---

# Query Semantic Model

Answer business questions by querying the org's live semantic model over the
`RevOS` MCP server and rendering the result directly in the chat.

The MCP server exposes a small set of generic tools; the semantic model is
reached through one of them, `api_read`, against the `cubes` resource:

| Call | What you get |
|---|---|
| `api_read({ resource: "cubes", method: "meta", params: {…} })` | the compiled semantic model — every cube/view with its measures, dimensions, segments and joins |
| `api_read({ resource: "cubes", method: "query", body: { query: {…} } })` | rows |

`api_details({ resource: "cubes", operation: "query" })` returns the exact
schema the endpoint enforces, read from its own OpenAPI document. When
something here disagrees with `api_details`, `api_details` is right — reach for
it whenever a call is rejected and the reason isn't obvious.

There is also `api_read({ resource: "cubes" })` with no `method`, which lists
the *stored cube definitions* — the YAML someone authored. That is a different
question from "what can I query"; for answering business questions you want
`meta`, always.

## Step 1: Discover what's queryable

Before guessing member names, read the catalogue. `meta` is a list endpoint
like any other, so project it down rather than pulling the whole document:

```json
{
  "resource": "cubes",
  "method": "meta",
  "params": { "fields": "name,title,description", "pageSize": 100 }
}
```

That is the whole catalogue at a few kilobytes — cheap to read and choose
from. `pageSize` maxes out at 100; if the response carries a
`metadata.nextPageToken`, pass it back as `params.pageToken` for the rest.

The catalogue can surface internal, system-generated cubes alongside the
business ones you'd expect — a helper cube backing a "latest scores" rollup,
an internal segment cube, or similar plumbing that exists to support another
cube's joins rather than to be queried directly. These usually stand out by a
sparse or missing description, or a mechanical-sounding name/title. When a
search matches both a clean, business-named cube and one of these, describe
and query the business one unless the question is specifically about the
internal one.

Then pull the full definition of the cube(s) the question needs, by dropping
`fields` and filtering to them:

```json
{
  "resource": "cubes",
  "method": "meta",
  "params": { "filter": "name == \"gold_order_items_enriched\"" }
}
```

That returns the exact `measures`, `dimensions` (with time granularities where
relevant), `segments`, and `joins` you can reference — always addressed as
`<CubeName>.<member>`, e.g. `gold_order_items_enriched.count` or
`gold_order_items_enriched.order_date`. See Step 2 for what `joins` gives you,
and what it doesn't.

`params.filter` is a CEL expression over `name`, `title`, `description` and
`type` — `name.contains("invoice")`, `!name.endsWith("_local")`,
`type == "view"`. **Members are not filterable**: you cannot search for a cube
by the fields it carries, which is why the projected catalogue above is the
way in.

If the user's question is purely about discovery — "what's in my semantic
model", "what can I query", "list the cubes/datasets" — stop here: summarize
the cubes (and their fields, if you pulled a full definition) in prose or a
short table, and skip Steps 3–6. Don't run a query the user didn't ask for.

Never hardcode or guess a member name. If the question can't be answered from
what `meta` returns, say so — don't invent a field.

**Stay on the semantic model even when the question names a source system.** A
question like "how many distinct HubSpot owners have at least one contact"
names HubSpot, but it's still an aggregate question — answer it from the
semantic model (e.g. a `users` cube built from `gold_contacts`, already
deduplicated and fully synced), not by reaching for a direct
HubSpot/Zammad/Exact Online/other source connector, even if one is available
and matches the question's wording better on a keyword search. A direct source
connector typically paginates and returns a partial live snapshot rather than
the full synced dataset — swapping to one mid-task can silently return an
answer wrong by orders of magnitude, with no error surfaced, because the
connector call itself succeeds fine; it's just not looking at the same data the
semantic model would. Reserve a direct source connector for a point lookup of
one already-identified record (e.g. "what's contact X's email", "who owns
company Y in HubSpot") — never for a count, sum, or breakdown across the
dataset.

## Step 2: Crossing cubes — read `joins`, and know its two blind spots

`meta` returns a `joins` array per cube — `{ name, relationship, sql }` for
every other cube it connects to. Read it before writing a query that spans
more than one cube: if a question needs `gold_order_items_enriched` and
`gold_users_with_order_stats` together, pull one of them and check whether the
other shows up in its `joins`. Don't infer a relationship just because two
cubes each happen to have a similarly-named "account id"-shaped column.

Two blind spots, and both will bite you if you trust `joins` as a complete
picture:

**Only outgoing joins are listed.** A cube reports the joins *it* declares,
not the ones other cubes declare pointing *at* it. Joins in this codebase are
written one-directionally — `deals` declares a join to `customers`, but
`customers` declares none back — while Cube's planner walks such a join from
either side. So a dimension-style cube that everything joins to can report
**zero** joins while being joinable from a dozen places. Never read an empty
or short `joins` array as "this cube doesn't connect to anything": check the
*other* cube's `joins` too before concluding there is no path.

**A fabricated `joinHints` path is not rejected.** `joinHints` pins the route
when more than one path connects two cubes: a list of paths, each an ordered
array of cube names to route through — two for a direct join, more for a
multi-hop — e.g. `[["gold_order_items_enriched", "gold_users_with_order_stats"]]`
or `[["orders", "line_items", "products"]]`. A pair in that path with no
declared join behind it does **not** produce an error: Cube falls back to
auto-resolving the real path, and you get an answer computed over a route you
did not choose. That is harmless when only one real path exists — Cube ignores
the bogus hint and gets it right anyway — and silently wrong the moment the
schema has a genuine fork between two valid paths, because the fabricated hint
doesn't reliably pin either one. **The query succeeding is not evidence the
path was real.**

So: set `joinHints` only when every consecutive pair in it is an edge you
actually saw in some cube's `joins` — having checked both directions, per the
first blind spot. When more than one plausible route exists — two paths to the
same field, or a fact table that could reach a dimension both directly and
through a third cube — **don't silently pick one**. State the ambiguity
plainly and ask the user to confirm the intended relationship or grain — e.g.
"revenue per order item" vs. "revenue per user" — before running the query.
Whenever you do set `joinHints`, say so in your explanation afterward — which
path you used and why — so the user can catch a wrong assumption. Prefer the
simplest single-cube answer whenever the question doesn't actually require
crossing cubes at all.

## Step 3: Build the query

The Cube.js query goes in `body.query` — note the nesting; the body is
`{ "query": { … } }`, not the query object itself.

| Field | Shape | Notes |
|---|---|---|
| `measures` | `string[]` | quantities to aggregate, e.g. `gold_order_items_enriched.count` |
| `dimensions` | `string[]` | attributes to group/break down by |
| `segments` | `string[]` | named filters from `meta`, layered on top like an extra filter |
| `timeDimensions` | `[{ dimension, granularity?, dateRange? }]` | see below |
| `filters` | see below | leaf conditions, optionally nested in `and`/`or` groups |
| `order` | `[[member, dir], …]` or `{ member: dir }` | either shape works — array of `[member, "asc"\|"desc"]` pairs, or an object map |
| `joinHints` | `[[cube, …], …]` | pins an ambiguous join path — each entry is an ordered path of cube names (two or more), see Step 2 |
| `limit` | `number` | see "Row limits" below |
| `offset` | `number` | for paging past `limit` |
| `timezone` | IANA string, e.g. `Europe/Amsterdam` | defaults to UTC |
| `total` | `boolean` | also returns the total matching row count, ignoring `limit`/`offset` — useful for "(showing 10 of 842)" |
| `ungrouped` | `boolean` | returns raw rows without aggregating by the dimensions, for inspecting individual records rather than summarizing — the row limit still applies |

Keys not listed here are forwarded to Cube unchanged, so a Cube.js feature the
API does not name is still reachable.

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

These are Cube's own filters, on `body.query.filters`, and they are forwarded
to Cube rather than validated against a schema here — a malformed one comes
back as Cube's error, not a neat parameter complaint. Don't confuse them with
the `params.filter` CEL string from Step 1: that one filters the *catalogue*,
this one filters the *data*.

### Row limits

`limit` is passed through to Cube, which applies its own default when the
query names none and rejects anything above its configured maximum. Those
defaults are sized for a data warehouse, not a chat window. Two consequences:

- **Always name the `limit` you actually want.** An open-ended query with no
  `limit` can return thousands of rows straight into the conversation.
- **`metadata.limit` in the response is the authority** — it reports the limit
  Cube actually applied, which is the number to quote when you say a result
  was truncated.

### Examples

Simplest possible:

```json
{
  "resource": "cubes",
  "method": "query",
  "body": { "query": { "measures": ["gold_order_items_enriched.count"] } }
}
```

Top N by category:

```json
{
  "resource": "cubes",
  "method": "query",
  "body": {
    "query": {
      "measures": ["gold_order_items_enriched.count"],
      "dimensions": ["gold_order_items_enriched.traffic_source"],
      "order": [["gold_order_items_enriched.count", "desc"]],
      "limit": 10
    }
  }
}
```

Time series (the chart-friendliest shape):

```json
{
  "resource": "cubes",
  "method": "query",
  "body": {
    "query": {
      "measures": ["gold_order_items_enriched.revenue"],
      "timeDimensions": [
        {
          "dimension": "gold_order_items_enriched.order_date",
          "granularity": "month",
          "dateRange": "last 12 months"
        }
      ]
    }
  }
}
```

Filtered with OR logic ("either refunded or a test order"):

```json
{
  "resource": "cubes",
  "method": "query",
  "body": {
    "query": {
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
  }
}
```

Crossing cubes with a pinned join path (see Step 2):

```json
{
  "resource": "cubes",
  "method": "query",
  "body": {
    "query": {
      "measures": ["gold_order_items_enriched.revenue"],
      "dimensions": ["gold_users_with_order_stats.country"],
      "joinHints": [["gold_order_items_enriched", "gold_users_with_order_stats"]]
    }
  }
}
```

Rules of thumb:

- One measure + one dimension → chart candidate by category.
- One measure + one `timeDimensions` with `granularity` → chart candidate over time.
- Multiple measures or multiple dimensions → table only; don't try to chart it.
- Always set `limit` explicitly for "top N" questions (`limit: N` + matching
  `order`), and never rely on the default for an open-ended pull.

## Step 4: Run the query and read the response

The response is `{ data, metadata }`:

- **`data`** — the array of rows, each a flat object keyed by the same member
  names used in the query.
- **`metadata.rowCount`** — how many rows came back.
- **`metadata.limit`** / **`metadata.offset`** — what Cube actually applied.
- **`metadata.total`** — present **only** if the query set `total: true`. It
  is the count of matching rows ignoring limit and offset, so
  `offset + rowCount < total` is how you tell there is another page. Without
  it, a page that fills exactly is indistinguishable from one ending on the
  last row — so set `total: true` whenever you intend to say "showing 10 of N"
  or to offer paging.
- **`metadata.lastRefreshTime`** — when the underlying data was last
  refreshed. Worth mentioning if the user asks how current the numbers are.
- **`metadata.annotation`** — Cube's own description of each member, grouped
  as `measures` / `dimensions` / `segments` / `timeDimensions` and keyed by
  the same fully qualified names the rows use, carrying at least `title`,
  `shortTitle` and `type`. **The rows carry values only**, so this is where
  human column headers and value types come from — use `shortTitle` for table
  headers instead of printing raw member names, and `type` to decide whether a
  column is a number to right-align and format.

If the call errors, surface the message plainly. Common causes: a mistyped
member name (re-read `meta`), a `dateRange`/`granularity` used against a
dimension that isn't a time dimension, or a `limit` above Cube's maximum. Note
what is *not* in that list: a bogus `joinHints` path doesn't error (Step 2), so
a clean result never confirms the path was right. When a message isn't
self-explanatory, call `api_details({ resource: "cubes", operation: "query" })`
and check your shape against what the endpoint actually accepts.

## Step 5: Render the result in chat

### 5a. Table — always

Render every returned row as a standard Markdown table, not ASCII art — it
renders natively in the chat UI and needs no manual column-width math. Take
headers from `metadata.annotation` (`shortTitle`) rather than printing raw
member names. Right-align numeric columns with the `---:` header-separator
syntax. Format numbers with thousands separators; round to 2 decimals when not
integral.

```markdown
| Traffic Source | Count |
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

- Never hardcode cube or member names — always confirm against `meta` first.
- Answer aggregate/analytical questions from the semantic model even when the
  question names a source system (HubSpot, Zammad, Exact Online, …) — don't
  switch to a direct source connector mid-task; that's for point lookups of
  one already-known record, not dataset-wide counts (see Step 1).
- Never silently resolve an ambiguous multi-cube join — ask the user (see
  Step 2).
- Never read an empty `joins` array as "no relationships": only outgoing joins
  are listed, so check the other cube too (see Step 2).
- Confirm every `joinHints` hop against a declared join before setting it. A
  fabricated pair is accepted and answered, not rejected — the query
  succeeding tells you nothing about whether the path was real (see Step 2).
- Prefer clearly business-named cubes over internal/system-generated ones
  when several match a search (see Step 1).
- Always render the table; render the chart only when the data shape supports
  it.
- Always set `limit` deliberately; the endpoint applies Cube's own default,
  which is far larger than a conversation wants.
- Set `total: true` whenever you plan to report "N of M" or offer another page.
- `api_details` is the authority on what the endpoint accepts — use it when a
  call is rejected rather than guessing at the shape.
- This is a read-only, in-chat skill — no file writes, no local project, no
  YAML. Reading the semantic model uses `api_read` only; the MCP server also
  exposes `api_write` and `api_delete`, and this skill never calls them.
- If `meta` returns no cubes, tell the user their organization doesn't appear
  to have a semantic model set up yet — don't guess why.
