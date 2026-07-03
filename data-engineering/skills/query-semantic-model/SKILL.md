---
name: query-semantic-model
description: >
  Run a Cube.js query against the semantic model and show the result inline in chat as
  an ASCII table and (where it makes sense) an ASCII bar chart. Use whenever the user
  asks a business question that can be answered from the cubes — "how many orders…",
  "top N…", "revenue by…", "trend over time", "compare X to Y" — or explicitly asks to
  "query the semantic model", "run a cube query", "show me a chart", "plot…", "graph…".
  Discovers measures and dimensions via `revos cubes meta`, executes the query with
  `revos cubes query`, and renders the results without leaving the chat.
---

# Query Semantic Model

Answer business questions by querying the org's semantic model and rendering the result
directly in the chat — no notebook, no UI hop. The CLI already exposes everything you
need: `revos cubes meta` lists the available cubes / measures / dimensions, and
`revos cubes query` runs a Cube.js query and returns the rows.

This skill is the "last mile" after Bronze → Silver → Gold → Cubes have been built and
applied. It turns the semantic model into something you can actually look at.

---

## Step 1: Discover what's queryable

Before guessing member names, list what the org's semantic model actually exposes:

```bash
revos cubes meta --json
```

The response carries an array of cubes, each with `measures`, `dimensions`, `segments`,
and a `name`. Cube members are addressed as `<CubeName>.<member>` — for example
`gold_order_items_enriched.count` or `gold_order_items_enriched.order_date`.

Pick the cube and members that match the user's question. If the question can't be
answered from the available members, say so — don't invent member names.

### Map the join graph from the local cube files

`revos cubes meta` tells you which members exist; the local `cubes/` folder tells you
**how cubes are connected**. Read every `*.yml` file in `cubes/` and pull out each
cube's `joins:` block — that's how the user-defined part of the semantic model is
wired up. Example:

```yaml
# cubes/gold_order_items_enriched.yml
apiVersion: revos/v1
kind: Cube
metadata:
  name: gold_order_items_enriched
spec:
  name: gold_order_items_enriched
  joins:
    gold_users_with_order_stats:
      relationship: many_to_one
      sql: "${CUBE}.user_id = ${gold_users_with_order_stats}.user_id"
    gold_product_performance:
      relationship: many_to_one
      sql: "${CUBE}.product_id = ${gold_product_performance}.product_id"
```

From this you can compute, for any pair of cubes, how many distinct join paths exist
between them. That's what lets you pick the right path in Step 2 instead of letting
Cube.js guess one for you.

**Caveat — system cubes are not in `cubes/`.** RevOS generates a handful of cubes
server-side (scoring, segments, model overlays, pre-aggregation overlays). Those
never appear as YAML in the project. The full member list is only visible through
`revos cubes meta`. So:

- Use the `cubes/` folder to **see the user-defined join graph**.
- Use `revos cubes meta` to **see every member that can actually be queried**,
  including system cubes.

When the user's question touches a system cube (e.g. "show me users by segment",
"top scoring entities"), the join graph from `cubes/` will be incomplete. Don't
assume there's no path — list the meta and look for it there.

---

## Step 2: Build the query — and pin the join path when it matters

A Cube.js query is a JSON object. The shapes you'll use most often:

```json
{ "measures": ["gold_order_items_enriched.count"] }
```

```json
{
  "measures": ["gold_order_items_enriched.count"],
  "dimensions": ["gold_order_items_enriched.traffic_source"],
  "order": { "gold_order_items_enriched.count": "desc" },
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
- Multiple measures or multiple dimensions → render as an ASCII table only; don't try
  to draw a chart.
- Always cap with `limit` (default 20) so a stray query can't return a million rows.

### Join paths — and how to pin them with a hint

Cube.js infers the join path from the cubes that appear in `measures` /
`dimensions` / `filters`. **When more than one path connects them, Cube.js picks
one for you — and the answer changes depending on which.** This is the single
biggest source of "the number looks wrong" bugs in a semantic-model query.

You spell the path out by prefixing the member with the cubes you want Cube.js to
walk through, dot-separated. The last segment is the actual member; everything
before it is the join hint. Examples:

```text
# no hint — Cube.js picks a path
gold_users_with_order_stats.lifetime_revenue

# hint: reach lifetime_revenue via the fact spine, then the users mart
gold_order_items_enriched.gold_users_with_order_stats.lifetime_revenue
```

The hint syntax works the same on measures, dimensions, and filter members.

**When you need a hint (red flags):**

1. Two cubes in the query are connected by **more than one path** in `cubes/`.
   Common shape: a fact spine joins to two dimension cubes, and one of the dimension
   cubes _also_ joins to the other (e.g. orders → users, orders → products,
   products → users via `last_purchaser_id`). Without a hint, Cube.js may pick the
   non-obvious path and quietly double- or under-count.
2. The user's question implicitly names the path ("revenue **per order item** by
   user country" vs "revenue **per user** by user country") — different grains,
   different paths, different numbers.
3. Counts come back smaller than the smallest cube would allow, or larger than the
   largest fact would allow. That's a sign Cube.js fanned out through the wrong
   join.
4. The cube has a many-to-many relationship in the chain. Always pin it.
5. You added a measure and the number changed dramatically (more than ~10%) without
   the dimension set changing — Cube.js probably re-routed the join.

**Worked example — same question, two answers.**

Cubes (from `cubes/`):

```text
gold_order_items_enriched  ──many_to_one──▶  gold_users_with_order_stats
gold_order_items_enriched  ──many_to_one──▶  gold_product_performance
gold_product_performance   ──many_to_one──▶  gold_users_with_order_stats   (last_purchaser_id)
```

Question: "Total revenue by user country."

```json
// Path A — order items → users directly (CORRECT for per-item revenue)
{
  "measures": ["gold_order_items_enriched.revenue"],
  "dimensions": [
    "gold_order_items_enriched.gold_users_with_order_stats.country"
  ]
}
```

```json
// Path B — order items → product → last_purchaser (WRONG: revenue gets
// attributed to the last buyer's country, not the actual buyer's)
{
  "measures": ["gold_order_items_enriched.revenue"],
  "dimensions": [
    "gold_order_items_enriched.gold_product_performance.gold_users_with_order_stats.country"
  ]
}
```

The two queries return wildly different numbers. Always state which path you used
and **why** in the explanation underneath the chart so the user can spot a wrong
choice.

**Worked example — filter via a specific path.**

```json
{
  "measures": ["gold_order_items_enriched.revenue"],
  "dimensions": ["gold_order_items_enriched.traffic_source"],
  "filters": [
    {
      "member": "gold_order_items_enriched.gold_users_with_order_stats.country",
      "operator": "equals",
      "values": ["DE"]
    }
  ]
}
```

**Rules for choosing a path:**

- Default to the **shortest** path that goes through the **fact spine** the
  question is naturally grained on (revenue per order → spine =
  `gold_order_items_enriched`; users with X → spine = `gold_users_with_order_stats`).
- Never silently take the alternate path. If two paths are plausible, ask the user
  which grain they meant before running the query.
- If `revos cubes meta` returns a member name that already contains dots (e.g.
  `cubeA.cubeB.foo`), that **is** the qualified form — paste it through verbatim,
  don't strip the prefix.

---

## Step 3: Run the query

```bash
revos cubes query --query '<INLINE_JSON>' --json
```

For anything longer than a one-liner, write the JSON to a temp file and pass it with
`@`:

```bash
cat > /tmp/q.json <<'EOF'
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
EOF
revos cubes query --query @/tmp/q.json --json
```

The response is the raw Cube.js payload — `data` is the array of rows, each row is a
flat object keyed by the same member names used in the query.

If the API returns an error, surface the message verbatim. Common causes: a member
name typo (re-check `revos cubes meta`), a cube that hasn't been applied yet
(`revos status` / `revos apply`), or a `dateRange` against a column that isn't a time
dimension.

---

## Step 4: Render the result in chat

Print **two** blocks in the assistant's reply, both as fenced code so they render
monospaced:

### 4a. ASCII table — always

Show every returned row. Right-align numeric columns, left-align everything else.
Format numbers with thousands separators; round to 2 decimals when not integral.
Truncate long string values to 32 chars with a trailing `…`.

```
traffic_source       count
─────────────────  ───────
Search             142,318
Organic             88,204
Email               41,907
Facebook            22,015
Display              9,471
```

### 4b. ASCII bar chart — when the shape allows

If the query returned exactly one measure plus exactly one dimension (categorical or
time), draw a horizontal bar chart underneath the table. Scale bars to a width of
**40 characters** based on the largest value in the result set; use the `█` block
character for filled cells and a single trailing space.

```
Search        ████████████████████████████████████████  142,318
Organic       ████████████████████████▊                  88,204
Email         ███████████▊                               41,907
Facebook      ██████▏                                    22,015
Display       ██▋                                         9,471
```

Time-series example (oldest → newest, top-to-bottom):

```
2025-06  ███████████▊                                   €  41,200
2025-07  █████████████████▏                             €  59,800
2025-08  ████████████████████▋                          €  72,400
…
```

Skip the chart (table only) when:

- The result set is empty.
- The query has 2+ measures, 2+ dimensions, or a single scalar value (no dimension).
- All measure values are zero or null.

For a single scalar answer (one row, one column), just say the number in prose
followed by the one-line table — no chart.

---

## Step 5: Explain the result briefly

After the rendered output, add 1–3 short sentences in plain English: what was
measured, the highest / lowest bucket, and any obvious anomaly (e.g. a missing month,
a single category dominating the total). Keep it to facts that are visible in the
table — don't speculate about causes.

If the user is likely to want to drill in, suggest **one** concrete follow-up query
they can ask for next ("Want the same broken down by country?"). Don't list more than
one — keep the chat tight.

---

## Rules

- Never hardcode cube or member names. Always confirm them via `revos cubes meta`
  before composing the query.
- Before composing a multi-cube query, scan the `joins:` blocks in `cubes/*.yml`. If
  the cubes you need are connected by more than one path, **pick one explicitly with
  a dotted join hint** instead of letting Cube.js guess.
- Remember that system cubes (scoring, segments, model overlays) live only in
  `revos cubes meta`, not in `cubes/`. Their joins aren't visible in the YAML —
  only in the meta output.
- Always render the table; render the chart only when the data shape supports it.
- Keep `limit` set (default 20). For "top N" questions, set `limit` to N and add
  `order` on the measure.
- Quote query JSON safely on the shell — prefer a temp file with `@/tmp/q.json` over
  a long inline string with embedded quotes.
- Don't write the query result to disk or invoke a Python plotter — this skill is
  in-chat only. For static PNG visualizations of the cube graph itself, use
  `visualize-semantic-model`.
- If `revos cubes meta` returns no cubes, stop and tell the user to run `revos apply`
  first.
