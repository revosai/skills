---
name: metrics
description: >
  Read, build, and fix RevOS dashboards of metric cards — the Metrics page of
  the app — through the RevOS MCP server. A card is one measure from the
  semantic model, counted over a segment's rows or the card's own conditions,
  optionally broken down by a dimension. Use this whenever the user wants to
  see what's on a dashboard ("what's on our sales dashboard", "what does the
  pipeline card show right now"), add a metric or KPI to a dashboard ("put
  open pipeline on the board", "add revenue by stage"), change, reorder, move,
  or remove a card, create, rename, or delete a dashboard, or asks why a card
  shows "unavailable", nothing, or a number that looks wrong — even if they
  never say "dashboard" or "card". Read it before the first api_write or
  api_delete on `dashboards` or `dashboard-cards`.
---

# Metrics

The app's **Metrics** page has two halves: a catalogue of every measure in the
semantic model, and **dashboards** of **cards**. Dashboards are shared by the
whole organization — there is no private dashboard, so anything you add or
change, everyone sees.

A card is:

| Field | What it is |
|---|---|
| `measure` | One **numeric** measure, fully qualified: `crm_deals.amount`. |
| `segmentId` | A segment whose rows the card counts, **or** — |
| `filter` | the card's own conditions (segment filter syntax). Never both. |
| `joinPaths` | The way to each other cube a condition or the breakdown reads: `{ "crm_companies": "crm_deals.crm_companies" }`. |
| `breakdown` | Optional dimension to split by: the card shows its top groups instead of one number. |
| `visualization` | How a breakdown shows: `bars` (default), `columns`, `donut`, `table`. |
| `title` | Shown instead of the measure's name. |
| `position` | Order on the dashboard, ascending. |

The card stores the **question**, never the answer: its value is computed by a
Cube query every time it's shown.

## Calling the tools

```json
// Dashboards
api_read   { "resource": "dashboards", "params": { "fields": "id,name,description" } }
api_write  { "resource": "dashboards", "data": { "name": "Sales", "description": "…" } }
api_write  { "resource": "dashboards", "id": "<dashboard id>", "data": { "name": "…" } }

// Cards — flat, not under the dashboard: list ONE dashboard's with a filter
api_read   { "resource": "dashboard-cards", "params": { "filter": "dashboardId == \"<dashboard id>\"", "pageSize": 200 } }
api_read   { "resource": "dashboard-cards", "id": "<card id>" }
api_write  { "resource": "dashboard-cards", "data": { "dashboardId": "…", "measure": "…" } }
api_write  { "resource": "dashboard-cards", "id": "<card id>", "data": { "title": "…" } }
api_delete { "resource": "dashboard-cards", "id": "<card id>" }
```

The record always goes under `data`. Cards come back ordered by `position`.
`api_details({ resource: "dashboard-cards", operation: "create" })` is the
authority on the body. A `403` on a write means the user's role is Viewer;
creating and changing dashboards and cards needs Member or higher.

## Reading a dashboard — and what its cards show now

1. Find the dashboard by name (`filter: "name == \"Sales\""`, or list them
   all — oldest first, and the first one is the one people land on).
2. List its cards.
3. For each card the user cares about, **compute the value** with
   `api_read { "resource": "cubes", "method": "query", "body": { "query": … } }`,
   building the query exactly as the app does — otherwise you report a
   different number than the one on their screen:

   ```json
   {
     "measures": ["<measure>"],
     "filters": [ <the segment's or the card's conditions, as Cube filters> ],
     "joinHints": [ <each joinPath, split on "."> ]
   }
   ```

   - **Card's own `filter`** — translate each condition with the table in the
     segments skill's `references/filter-syntax.md` (`EQUAL` → `equals`,
     `EMPTY` → `notSet`, …). Top-level `AND` items are separate entries in
     `filters`; an `OR` (root or group) becomes `{ "or": [ … ] }`. Skip
     conditions with no `member`, or no `value` where the operator needs
     one — the app ignores them too.
   - **Dynamic segment** — `api_read` the segment and use *its* `filter` the
     same way; its `cubes[1..].joinPath` go into `joinHints` **before** the
     card's own `joinPaths`.
   - **Static segment** — one filter instead:
     `{ "member": "segment_<segment id, '-' → '_'>.id", "operator": "set" }`.
     Its conditions don't apply; the snapshot does.
   - **`joinHints`** — each path as an array, `"crm_deals.crm_companies"` →
     `["crm_deals", "crm_companies"]`; a path that's just the measure's cube
     needs none. Leave `joinHints` out when there are none.
   - **No rows** — a count, count distinct, or sum is `0`; an average or
     other measure has no value. Say "no value", not `0`.

4. **Breakdown** — the same query plus the dimension:
   - a non-time dimension: `"dimensions": ["<breakdown>"]`,
     `"order": { "<measure>": "desc", "<breakdown>": "asc" }`. The card
     shows the top 5 and folds the rest into "Other" — only for `count` /
     `sum` measures whose breakdown doesn't fan out (below); otherwise the
     groups don't add up to the total, and the card doesn't pretend they do.
   - a time dimension: `"timeDimensions": [{ "dimension": "<breakdown>",
     "granularity": "month" }]`, `"order": { "<breakdown>": "desc" }` —
     latest months first.

Render a value with the measure's `format` from `meta` (currency, percent),
and a breakdown as a small table or chart. Say which segment or conditions
the number is counted over — "€1.2M open pipeline, deals in the EMEA
segment" — because a bare number invites the wrong comparison.

## Adding a card

1. **Pick the measure.** Read the catalogue
   (`cubes` `meta`, `fields: "name,title,description"`), then the cube's
   full `meta`. The measure must be `type: "number"` — a string, boolean, or
   time measure is rejected. Prefer business-named cubes over generated
   plumbing (table views `model_…`, segment snapshots `segment_…`). If no
   measure says what the user means ("win rate", "ARR"), say so and offer the
   closest, or adding one with the cubes skill — don't approximate silently.
2. **Decide what it counts over.**
   - An existing **segment** when the user names an audience that already
     exists, or the condition is one a segment already captures. The
     segment's **root cube must be the measure's cube**
     (`segment.cubes[0].joinPath == "<measure's cube>"`) — the server
     doesn't check this, and the app shows such a card as unavailable. A
     static segment also needs its `segment_…` cube to be in `meta`.
   - Otherwise the card's own **`filter`**, in segment syntax
     (`references/filter-syntax.md` in the segments skill). Check stored
     values with a cubes query before an `EQUAL` on a string — a wrong
     spelling saves fine and the card shows 0.
   - Neither: the card counts every row.
3. **Conditions on other cubes.** For each cube other than the measure's
   that a condition or the breakdown reads, add a `joinPaths` entry —
   key the cube name, value the dotted path from the measure's cube,
   checked hop by hop against `joins` in `meta`. If two routes exist, the
   choice changes the number: ask. Then two rules the server **doesn't**
   enforce, both of which the app flags as unavailable:
   - **No condition on a measure** (`crm_deals.count > 3`). On a card's
     total it isn't per-row; the app refuses to show it. Use a segment
     rooted elsewhere, or a dimension.
   - **No condition on a cube the measure's rows have many of**
     (`hasMany` / `one_to_many` along the path). Each counted row would be
     checked once per related row. A breakdown along such a join is allowed,
     but its groups can add up to more than the total — tell the user it may
     double count.
4. **Write it.** `dashboardId` and `measure` are required; send `segmentId`
   **or** `filter`, plus `joinPaths`, `breakdown`, `visualization`, and
   `title` when useful. Omit `position` to append. The server checks that the
   dashboard and segment exist and that every member named is in the model,
   and returns `400` with every problem at once — fix all of them, don't
   resend unchanged.
5. **Read it back and compute its value** as in *Reading*, so the user sees
   what the card will show — and so a broken one is caught now, not by them.

Before creating a card, list the dashboard's cards: if the same measure with
the same scope is already on it, point to that card instead of adding a
twin.

## Changing a card

Update with only the fields that change. `null` clears a field (`title`,
`segmentId`, `breakdown`, `visualization`); `filter` and `joinPaths` are
replaced whole, so start from a fresh read.

- **Switch from filter to segment**: `{ "segmentId": "…", "filter": {} }`.
  From segment to filter: `{ "segmentId": null, "filter": { … } }`. Sending
  both a segment and a non-empty filter is rejected.
- **Drop a condition or breakdown on another cube**: also drop its
  `joinPaths` entry, unless something else on the card still reads that cube.
- **Reorder**: set `position` between its new neighbours' values
  (e.g. `1.5` between `1` and `2`).
- **Move to another dashboard**: set `dashboardId`; without `position` it
  goes last.

The server checks only what the update names: editing a title doesn't
re-validate the rest.

## Why a card shows "unavailable" or a wrong number

Read the card (and its segment) and check, in this order — the app's own:

1. **Measure gone** — `measure` not in `meta` (renamed or removed cube).
2. **Segment gone** — `segmentId` no longer resolves.
3. **Field gone** — a condition's member (or the segment's), the breakdown,
   or a static segment's `segment_…` cube is not in `meta`.
4. **Condition on a measure** — in the card's or a dynamic segment's filter.
5. **Join gone** — a `joinPaths` / segment path hop the model no longer
   declares.
6. **Condition on a fan-out** — a condition on a cube the measure's rows have
   many of.

Fix it with an update (point at the renamed member, drop the condition), or
say what has to change in the model. For a number that looks wrong but isn't
flagged: compare the query you built with the user's expectation — the wrong
join route (ask which they mean), a static segment that hasn't been
re-snapshotted, a string value spelled differently from the stored one, or a
fanned-out breakdown. Check `metadata.lastRefreshTime` on the query result
for stale data.

## Deleting

- **A card**: `api_delete` on `dashboard-cards`. Name the card back
  (title or measure, scope, dashboard) and get a yes.
- **A dashboard** removes **every card on it**. List its cards, tell the user
  how many and which, and that the whole organization loses it, then ask for
  an explicit yes for this dashboard.

No undo for either. A card or dashboard you created yourself in a failed
attempt is no exception — say so and ask before deleting it.

## Creating a dashboard

`name` (1–255 chars) and an optional `description`. Check for a namesake
first and ask if one exists. Since every dashboard is org-wide, don't create
one just to try something out.
