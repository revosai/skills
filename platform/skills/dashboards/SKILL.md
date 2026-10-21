---
name: dashboards
description: >
  Read, build, and fix RevOS dashboards of metric cards through the RevOS MCP
  server. A card is one metric (a numeric measure), counted over a segment's
  rows or the card's own conditions, optionally broken down by a dimension.
  Use this whenever the user wants to see what's on a dashboard ("what's on
  our sales dashboard", "what does the pipeline card show"), put a metric or
  KPI on one ("add open pipeline to the board", "add revenue by stage as a
  donut"), change, reorder, move, or remove a card, create, rename, or delete
  a dashboard, or asks why a card shows "unavailable" or a number that looks
  wrong — even if they never say "dashboard" or "card". Read it before the
  first api_write or api_delete on `dashboards` or `dashboard-cards`.
---

# Dashboards

Dashboards are shared by the whole organization — there is no private one, so
anything you add or change, everyone sees. Each holds ordered **cards**:

| Field | What it is |
|---|---|
| `measure` | One **numeric** measure, fully qualified: `crm_deals.amount`. |
| `segmentId` | A segment whose rows the card counts, **or** — |
| `filter` | the card's own conditions (segment filter syntax). Never both. |
| `joinPaths` | The way to each other cube a condition or the breakdown reads: `{ "crm_companies": "crm_deals.crm_companies" }`. |
| `breakdown` | Optional dimension: the card shows its top groups instead of one number. |
| `visualization` | How a breakdown shows: `bars` (default), `columns`, `donut`, `table`. **Never send it without `breakdown`**: a card with no breakdown is a single number whatever this says. |
| `title` | Shown instead of the measure's name. |
| `position` | Order on the dashboard, ascending. |

**Hard rule: never write `visualization` without `breakdown`.** A card with
no breakdown is a single number, whatever its visualization says. Asked for a
chart (bars, columns, a donut) without a field to split by, ask which field
and write nothing until the user answers.

A card stores the **question**, never the answer. How to pick a metric, scope
it, and compute its value is the **metrics skill** — read it before adding a
card or reporting what one shows.

## Calling the tools

```json
// Dashboards
api_read   { "resource": "dashboards", "params": { "fields": "id,name,description" } }
api_write  { "resource": "dashboards", "data": { "name": "Sales", "description": "…" } }
api_write  { "resource": "dashboards", "id": "<dashboard id>", "data": { "name": "…" } }
api_delete { "resource": "dashboards", "id": "<dashboard id>" }

// Cards — flat, not under the dashboard: list ONE dashboard's with a filter
api_read   { "resource": "dashboard-cards", "params": { "filter": "dashboardId == \"<dashboard id>\"", "pageSize": 200 } }
api_read   { "resource": "dashboard-cards", "id": "<card id>" }
api_write  { "resource": "dashboard-cards", "data": { "dashboardId": "…", "measure": "…" } }
api_write  { "resource": "dashboard-cards", "id": "<card id>", "data": { "title": "…" } }
api_delete { "resource": "dashboard-cards", "id": "<card id>" }
```

The record always goes under `data`. Dashboards list oldest first — the first
is the one people land on; cards come back by `position`.
`api_details({ resource: "dashboard-cards", operation: "create" })` is the
authority on the body. Reading needs Viewer; any write needs Member — a `403`
means the user's role can't change dashboards.

## Reading a dashboard

Find it by name (`filter: "name == \"Sales\""`), list its cards, and for
each card the user cares about compute its value as the metrics skill
describes — scope from `segmentId` or `filter`, join hints from the segment's
paths and then the card's `joinPaths`, breakdown from `breakdown`. Report
each card by its `title` (or the measure's title), its value, and what it's
counted over.

## A chart needs a breakdown

When the user wants bars, columns, a donut or "a visualization" — on a new
card or an existing one — send `breakdown` **and** `visualization` together,
never `visualization` alone: it saves fine and the card stays a bare number
(a title that names a split doesn't make one either). Take the dimension from
what they said ("by pipeline", "by stage"); if they named none, offer two or
three fitting dimensions from `meta` and ask — don't pick one yourself, and
write nothing until they answer. Before saying the card shows a chart, check
the read-back has `breakdown` set.

## Adding a card

1. **List the dashboard's cards.** If the same measure with the same scope is
   already there, point to it instead of adding a twin.
2. **Pick the metric and scope** with the metrics skill: a numeric measure;
   a segment rooted at the measure's cube, or conditions, or nothing; a join
   path per other cube read; no condition on a measure or on a cube the rows
   have many of.
3. **Write it.** `dashboardId` and `measure` are required; add `segmentId`
   **or** `filter`, `joinPaths`, `breakdown`, `visualization`, `title` as
   needed. Omit `position` to append. A `visualization` goes in only with a
   `breakdown`; asked for a chart with no field named, stop here and ask
   which one (see above).

   The server checks that the dashboard and segment exist, that the measure
   is a numeric measure, the breakdown a dimension, every condition names a
   `member` that exists, and that segment and filter aren't both set — a
   `400` lists every problem at once; fix them all, don't resend unchanged.
   It does **not** check the segment's root, measure conditions, fan-out, or
   `joinPaths`: those save fine and the app shows the card as unavailable.
4. **Read it back and compute its value**, so the user sees what the card
   shows — and a broken card is caught now, not by them.

## Changing a card

Send only the fields that change. `null` clears `title`, `segmentId`,
`breakdown`, `visualization`; `filter` and `joinPaths` are replaced whole, so
start from a fresh read.

- **Filter → segment**: `{ "segmentId": "…", "filter": {} }`.
  **Segment → filter**: `{ "segmentId": null, "filter": { … } }`.
- **Dropping a condition or the breakdown on another cube**: drop its
  `joinPaths` entry too, unless something else on the card still reads that
  cube.
- **Reorder**: a `position` between the new neighbours' (`1.5` between `1`
  and `2`).
- **Move**: set `dashboardId`; without `position` it goes last.

The server checks only what the update names: retitling doesn't re-validate
the rest.

## Why a card is unavailable or looks wrong

The model and segments change under cards — nothing repairs them, and a
segment or cube can be deleted without touching the cards that use it. Read
the card (and its segment), then check in the app's order:

1. **Metric gone** — `measure` not in `meta`.
2. **Segment gone** — `segmentId` doesn't resolve.
3. **Field gone** — a condition's member (the card's or a dynamic segment's),
   the breakdown, or a static segment's `segment_…` cube isn't in `meta`.
4. **Condition on a measure** — in the card's or a dynamic segment's filter.
5. **Join gone** — a hop in `joinPaths` or the segment's paths the model no
   longer declares.
6. **Condition on a fan-out** — a condition on a cube the rows have many of.

Fix it with an update (repoint to the renamed member, drop the condition,
switch scope), or say what has to change in the model. A number that's
flagged by nothing but looks wrong: the other join route, a static segment
not re-snapshotted, a string value spelled differently from the stored one,
a fanned-out breakdown, or stale data (`metadata.lastRefreshTime`).

## Creating, renaming, deleting dashboards

- **Create**: `name` (1–255 chars), optional `description`. Check for a
  namesake first and ask if one exists. Everyone sees it — don't create one
  just to try something.
- **Rename**: `name` / `description` only.
- **Delete a card**: name it back (title or measure, scope, dashboard) and
  get a yes.
- **Delete a dashboard**: it removes **every card on it**. List them, tell
  the user how many and which, and that the whole organization loses them,
  then ask for an explicit yes for this dashboard.

No undo for any delete. A card or dashboard you created yourself in a failed
attempt is no exception — say so and ask before deleting it.
