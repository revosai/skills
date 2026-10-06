# Columns and streams

`api_details({ resource: "tables", operation: "update" })` has the exact
JSON schema. This page covers what it can't show.

## Every column

```json
{ "name": "industry", "displayName": "Industry", "type": "string",
  "external": true, "streamId": "crm_companies", "path": "industry" }
```

- **`name`**: becomes a warehouse column name, so it must match
  `^[a-zA-Z_][a-zA-Z0-9_]*$`, be unique in the table, and not be `scores`
  (reserved for scoring output). Put the human label in `displayName`:
  `deal_owner_emea` with "Deal owner (EMEA)".
- **`id`**: omit it for a new column, and the server generates one. Keep it
  unchanged on every existing column. Views, filters, scoring features, and
  action templates refer to columns by id. The JSON schema shows a fixed
  `default` for `id`; never copy that value.
- **`type`**: one of `string`, `number`, `boolean`, `date`, `dateTime`, or
  `action`. It's `dateTime`, camel-cased; `datetime` is rejected. There is
  no `formula` type any more. A derived value is a cube member: add it to
  the cube, then bind a column to it.
- **`format`**: display only. One of `percent`, `currency`, `id`, `link`, or
  a d3-format string for numbers.
- **`hidden`** and **`pinned`** (`left` / `right`) may ride along on a table
  update. They set the column's initial layout in the views.

## External columns: read from a cube

- **`external: true`**.
- **`streamId`**: the `id` of one of the table's streams, which is a cube
  name.
- **`path`**: the member's name inside that cube, without the cube prefix,
  exactly as the cube defines it (`industry`, `close_date`). Read it from
  the cube (`api_read` on `cubes`, or `meta`). Never compose it. A `path`
  the cube doesn't have breaks the org's model.
- **`type`**: pick it from the member:

  | cube member | column `type` |
  |---|---|
  | `string` | `string` |
  | `number` | `number` |
  | `boolean` | `boolean` |
  | `time` | `dateTime`, or `date` if it's a calendar date |

- **`measure: true`**: exactly when the member is a **measure** (listed
  under `measures`), such as "number of deals" on a companies table
  (`crm_deals.count`). The type is then `number`. `measure` is rejected
  without `external: true`.

## Stored columns: kept in RevOS

Leave `external` out (or `false`) and leave out `streamId` and `path`.
Values are typed in the UI or written by actions. A stored column needs no
stream: RevOS keeps the table's stored columns (and its scores) in a cube of
the table's own, `model_stream_<table id, - → _>___local`, which exists only
while the table has one of them. Never name a table's own cube in its own
`streams` (another table's own cube is fine; see *Streams*), and never send
a `__local` stream or `streamId: "__local"`; both are obsolete and
dropped.

## Action columns

```json
{ "name": "enrich_company", "displayName": "Enrich company", "type": "action",
  "config": { "actionId": "<from api_read actions>", "version": "1",
              "params": { "objectType": "company" },
              "input": { "domain": "{{<id of the domain column>}}" } } }
```

- `actionId`: from `api_read { "resource": "actions" }`. Read the action
  with `get` to see which `params` and `input` keys it expects.
- **`input`** is rendered per row with Liquid. Row values are addressed by
  the **column's `id`**, not its name: `{{cm123abc}}`, or
  `{{cm123abc.property}}`. A template that names a column (`{{domain}}`)
  renders empty.
- **`params`** is set once for the whole column, with no Liquid. A
  per-row value here produces the same wrong input on every row, silently.
- Adding the column doesn't run it. Running is `api_write` on
  `action-runs`, which acts on connected systems, so only do that when the
  user asks.

## Streams

```json
"streams": [
  { "id": "crm_deals" },
  { "id": "crm_companies", "joinPath": "crm_deals.crm_companies" }
]
```

A stream is `id` and `joinPath`, nothing else. Older tables and docs carry
`connectionId` and `streamName` on it; they're dropped on write, so don't
send them. The cube says where its data comes from, not the table.

- **`id`** is the **cube name**. Schema generation builds the view's join
  paths from it, so an id that isn't a real cube breaks the org's model.
- **The first stream is the root.** Every other stream is reached from it.
  Never give the root a `joinPath`, because it is dropped. Don't reorder
  streams: that changes what a row is.
- **`joinPath`**: the dotted path of cube names from the root to this
  stream, one hop per declared join (`crm_deals.crm_companies`, or
  `crm_contacts.crm_companies.crm_regions`). Always send it on a non-root
  stream. One sent without it is stored as `<root id>.<stream id>`, which
  is wrong whenever the cube isn't joined straight onto the root.
  - Check every hop against the cubes' `joins`. A join can be declared on
    either side of the pair, so look at both cubes before concluding there
    is none.
  - If there's no path, the join has to be added to a cube first (the cubes
    skill).
  - If there are two paths, ask which relationship the user means.
- **Fan-out.** Before joining a cube in for a dimension, check that each
  root row has *one* of it. That's SKILL.md rule 3, and the join can be
  declared on either side: `crm_deals → crm_companies: many_to_one` means
  each company has many deals. From a "many" cube, add only measures.
- A stream may be written before its columns, and stays until a column
  that read it is removed.
- **Another table's columns.** A stream may be another table's own cube,
  `model_stream_<other table id, - → _>___local`, to read that table's
  stored columns or `scores`. It's in `meta` only while that table holds
  something, and joins like any cube: check its `joins`, and the fan-out
  rule, as above.

## The `id` column every table has

```json
{ "name": "id", "type": "string", "external": true, "streamId": "<root cube>", "path": "<root's primary-key dimension>", "hidden": true }
```

Rows are identified by it, and an external `id` is what makes the first
stream the root. (A table whose `id` column is stored keeps its own rows
instead: its streams hang off its own cube, and their paths start with
`model_stream_…___local`. Never flip the `id` column's `external`: that
moves the root, and every path with it.)
Set `hidden: true` when the table also has a
`name` column. That column is
`{ "name": "name", "displayName": "Name", "type": "string", "external": true, "streamId": "<root>", "path": "<name dimension>" }`.
For the name dimension, use the cube's `meta.nameDimension`, or else a
dimension called `name`.
