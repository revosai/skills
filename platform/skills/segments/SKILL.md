---
name: segments
description: >
  Create, edit, and troubleshoot RevOS segments — saved audiences defined over
  the org's semantic model — through the RevOS MCP server, and attach them to a
  table so its rows are scoped. Use this whenever the user wants to save,
  define, or change an audience or list ("companies with an active
  subscription", "deals over 50k in the EMEA pipeline", "users who ordered
  twice"), add or change a condition on an existing segment, show only some
  rows in a table ("only the stalled deals", "filter this table to…"), or asks
  why a segment is FAILED, empty, or showing the wrong rows — even if they
  never say the word "segment". Read it before the first api_write on the
  `segments` or `table-views` resource.
---

# Segments

A segment is a saved audience: one row per record of a **root cube**, kept
when it matches a **filter**. It's defined over the semantic model (cubes),
not over a table — tables only borrow a segment to scope their rows.

You reach it through the RevOS MCP server's generic tools on the `segments`
resource: `api_read` lists and gets, `api_write` creates (no `id`) and updates
(with `id`). `api_details({ resource: "segments", operation: "create" })` is
the authority on the body shape; this skill covers what that schema can't
tell you.

The thing to keep in mind throughout: **the server barely validates a
segment when you save it.** Member names, join paths, and whether a condition
makes sense for the root are only checked by the RevOS UI's segment editor.
Over the API a broken segment saves with a 200 and then fails, or worse,
quietly matches the wrong records when it's evaluated. So the checks below
are yours to do before writing — and reading the segment back after writing
is how you find out what was actually saved.

## Calling the tools

The argument shapes matter more than usual here, because a key in the wrong
place is often **ignored rather than rejected** — a write with its body under
the wrong key can return success, bump the segment's version, and change
nothing.

```json
// List / get / named reads — `params` for query-string filters, `body` for a named read that takes one
api_read  { "resource": "segments", "params": { "filter": "name == \"Enterprise accounts\"" } }
api_read  { "resource": "segments", "id": "<segment id>" }
api_read  { "resource": "cubes", "method": "meta", "params": { "filter": "name == \"hubspot_deals\"" } }
api_read  { "resource": "cubes", "method": "query",
            "body": { "query": { "dimensions": ["hubspot_deals.properties_dealstage"], "limit": 20 } } }

// Create (no id) / update (with id) — the record always goes under `data`
api_write { "resource": "segments", "data": { "name": "…", "type": "DYNAMIC", "cubes": [ … ], "filter": { … } } }
api_write { "resource": "segments", "id": "<segment id>", "data": { "filter": { … } } }
```

`method` (not `operation`) selects a named read like `meta` or `query`; a
cubes query goes under `body.query`, never `params`.

## Creating a segment

### 1. Pick the root cube — it decides what one "member" is

"Companies that have a won deal" has companies as members; "won deals" has
deals as members. Same data, different audience. Choose the cube whose rows
are the things the user wants to end up with, and confirm with the user when
it's genuinely ambiguous — the root can't be changed after creation (doing
that means making a new segment).

Read the catalogue first, then the root's full definition:

```json
{ "resource": "cubes", "method": "meta", "params": { "fields": "name,title,description", "pageSize": 100 } }
{ "resource": "cubes", "method": "meta", "params": { "filter": "name == \"hubspot_companies\"" } }
```

The full definition gives you the members (always written
`<cube>.<member>`), each dimension's `type`, which dimension has
`primaryKey: true`, `meta.nameDimension` when the cube declares one, and the
cube's `joins`. Never guess a member name — they're per-organization.

Prefer business-named cubes over generated plumbing (`model_stream_…___local`
and the like) unless the user is clearly asking about one of those.

### 2. Build `cubes` — the root first, then one entry per other cube you filter on

```json
"cubes": [
  { "joinPath": "hubspot_companies", "primaryKeyDimension": "id", "nameDimension": "name" },
  { "joinPath": "hubspot_companies.hubspot_deals" }
]
```

- `cubes[0]` is the root. Its `joinPath` is just the cube name. Set
  `primaryKeyDimension` to the root's primary-key dimension (the member
  name without the cube prefix) and `nameDimension` to `meta.nameDimension`
  when the cube declares one, otherwise to a dimension literally called
  `name` if the cube has it — table creation from a segment uses both to
  build its `id` and `name` columns. If the root has no
  primary-key dimension, say so: the segment will evaluate on `id`, which
  may not exist.
- Every other cube a condition references gets an entry whose `joinPath` is
  the **dotted path from the root** to it, following `joins`:
  `"root.middle.target"`. Check each hop against a cube's `joins` — and
  remember a cube only lists joins *it* declares, so if `A` doesn't list `B`,
  look at `B`'s joins too before concluding there's no path.
- When there are two genuinely different routes to the same cube, the path
  you pick changes the answer. Don't silently choose — ask which relationship
  the user means.

### 3. Write the filter — and watch for fan-out

`filter` is RevOS's own condition format (not a Cube.js query):

```json
"filter": {
  "combinationMode": "AND",
  "items": [
    { "member": "hubspot_companies.industry", "type": "EQUAL", "value": "Software" },
    { "filterType": "Group", "combinationMode": "OR", "items": [
        { "member": "hubspot_companies.country", "type": "EQUAL", "value": "DE" },
        { "member": "hubspot_companies.country", "type": "EQUAL", "value": "AT" } ] }
  ]
}
```

The operator vocabulary, which operators fit which member types, date values,
and the validation rules the JSON schema doesn't show are in
[references/filter-syntax.md](references/filter-syntax.md) — read it before
writing any condition beyond a simple `EQUAL`. Two rules come up constantly:
there is **no multi-value "in"** (`value` is one string or number, so "DE or
AT" is an OR group as above), and `IS`/`IS_NOT` only take `TODAY`,
`IN_THE_FUTURE`, or `IN_THE_PAST`.

**Check the stored values before any `EQUAL` / `NOT_EQUAL` on a string.**
Matching is exact and case-sensitive, and the user's words ("active",
"enterprise", "won") are often not how the source stores them (`ACTIVE`,
`Enterprise`, `closedwon`). A wrong value doesn't error — the segment just
comes out empty. One cheap query shows what's really there:

```json
api_read { "resource": "cubes", "method": "query",
           "body": { "query": { "dimensions": ["stripe_subscriptions.status"], "limit": 20 } } }
```

Use the stored spelling, and if nothing matches the user's term, ask rather
than guess.

**Fan-out — the trap that saves fine and answers wrong.** If the root has
*many* of another cube (the root's `joins` entry, or the reverse, says
`hasMany`/`one_to_many`), a **dimension** condition on that cube doesn't mean
"members that have at least one such row" in any reliable way — it fans the
root out across the child rows and the UI refuses to save it for exactly this
reason. The API won't stop you.

Rephrase the condition as a **measure** on the child cube instead, which
aggregates per root row:

- "Organizations that have built at least 3 scoring models" →
  `{ "member": "revos_prod_ScoringModel.count", "type": "GREATER_THAN_OR_EQUAL", "value": 3 }`
- "Companies with any deal" → the deals cube's count `GREATER_THAN` `0`.

If the child cube has no measure that expresses the condition (e.g. "has a
deal in stage *won*" and there's no count-of-won-deals measure), don't write
the fanning dimension condition anyway. Tell the user plainly that the
semantic model doesn't support that condition from this root yet, and offer
what it does support — a segment rooted on the child cube instead (won
deals), or adding a measure to the cube.

Conditions on a cube the root has **one** of (`hasOne`/`belongsTo`) are fine
as dimension conditions.

### 4. Choose `type` — DYNAMIC unless the user insists

- **DYNAMIC** (use this by default): re-evaluated automatically by RevOS a
  few times a day, so it follows the data. A new or edited DYNAMIC segment
  shows `status: "PENDING"` until the next scheduled evaluation — say so,
  so the user isn't surprised by `objectCount` being empty right after
  saving.
- **STATIC** freezes the membership at evaluation time — but evaluating is
  something the MCP tools can't trigger. A STATIC segment created here stays
  `PENDING` until someone presses *Evaluate* in the RevOS UI, and while it's
  pending a table scoped to it shows **all** rows, unfiltered. Only create
  one when the user explicitly asks for a frozen snapshot, and tell them to
  run *Evaluate* in the UI before relying on it.

`type` can't be changed after creation.

### 5. Name it, write it, report back

`name` is required (1–255 chars); add a one-line `description` of the
audience in plain words. Before writing, check for a namesake —
`api_read({ resource: "segments", params: { filter: "name == \"…\"" } })` —
since segments can't be deleted from here, and a duplicate is clutter the
user has to clean up in the UI.

Then `api_write({ resource: "segments", data: { name, description, type, cubes, filter } })`.

**Read it back** with `api_read` by the returned `id` and compare its
`cubes` and `filter` to what you sent. They should match; if they don't, the
write didn't land the way you intended — fix the call rather than reporting
success.

Then tell the user, in a sentence or two: the root (what one member is), the
conditions in plain language, the type, and that it's `PENDING` until
evaluated. If you made a judgment call (a measure instead of a fanning
dimension, a particular join path), say which and why.

## Editing a segment

`api_write` with the segment's `id` and only the fields that change. The
catch: **each field you send replaces the stored one whole.** `filter` and
`cubes` are single fields — send a filter with one new condition and every
condition you left out is gone.

1. `api_read({ resource: "segments", id })` fresh, right before writing.
2. Start from its current `filter` (and `cubes`) and change only what the
   user asked for. A new string value gets the same stored-value check as
   on create (step 3 above) — the existing conditions' spelling is a hint,
   not proof of how the new value is stored.
3. If the new condition references a cube that isn't in `cubes` yet, add its
   `joinPath` entry and send the whole `cubes` array too. If you removed the
   last condition on some cube, drop that entry.
4. Don't send `type` — it isn't updatable — and don't try to change the root
   (`cubes[0]`); for a different root, create a new segment.
5. After the write, `api_read` the segment again and check the `filter` is
   the one you meant to save — a bumped `version` alone doesn't prove the
   change landed.

Every update bumps the segment's `version` (the UI can restore older
versions — worth mentioning if the user is nervous about an edit). A STATIC
segment goes back to `PENDING` when its filter or cubes change.

## Scoping a table's rows with a segment

Tables don't carry filters; their **view** does. To make a table show only a
segment's members, point the table's default view at the segment:

1. `api_read({ resource: "table-views", method: "list", id: "<TABLE id>" })` —
   the list hangs off the table, so it's the table's id here. Take the entry
   with `isDefault: true`.
2. `api_write({ resource: "table-views", id: "<that VIEW's id>", data: { "segmentId": "<segment id>" } })`.

A view holds either a segment or its own ad-hoc filter, never both; attaching
a segment is the better of the two. `"segmentId": null` detaches it. Use a
segment whose root cube is the cube the table's rows come from (its main
stream) — that's how the UI pairs them when it builds a table from a
segment. If the segment is STATIC and not `READY`, warn that the table will
show every row until it's evaluated.

## Troubleshooting a segment

`api_read` the segment and look at `status`:

- `PENDING` — saved, not evaluated yet. Normal right after a create or edit;
  DYNAMIC catches up on its own schedule, STATIC needs *Evaluate* in the UI.
- `EVALUATING` — in progress; check back.
- `FAILED` — `evaluationError` has the reason, usually Cube's. The common
  causes, in order of likelihood: a member that doesn't exist (re-read the
  cubes' `meta` and correct the name), a `joinPath` hop that isn't a real
  join, or a condition value of the wrong kind for its member. Fix the
  segment with an edit as above; it'll be re-evaluated on the next run.
- `READY` but the wrong members or count — the usual suspects are a fanning
  dimension condition (see step 3), a root cube that doesn't match what the
  user meant by "member", or a join path that took the other route.

## Deleting

Segments can't be deleted through these tools, on purpose. If the user wants
one gone, point them to the RevOS UI — and note that the UI will refuse while
a table view still uses it, so detach it first (`segmentId: null`) if that's
the case.
