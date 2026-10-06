---
name: tables
description: >
  Create, read, edit, and delete RevOS tables (scoring models), and scope
  their rows with a segment, through the RevOS MCP server. A table's rows
  come from a cube, and its columns are read from cubes, stored in RevOS, or
  filled by actions. Use this whenever the user wants a table or list in
  RevOS ("make a table of our companies", "a table of the stalled deals"),
  wants to add, change, rename, hide, or remove a column, pull a field from
  a related object into a table ("add the company's industry to the deals
  table"), add an action column, see how a table is built, or delete a
  table, even if they never say the word "table". Read it before the first api_write or
  api_delete on the `tables` or `table-views` resource.
---

# Tables

A table, called a scoring model in the API, is a set of **rows** with typed
**columns**:

- **Rows** come from the table's **root cube**: the cube of its first
  stream, so a companies table has one row per `crm_companies` record. A
  table that stores its own `id` column holds its own rows instead.
- **Columns** are one of three kinds:
  - **external**: read live from a cube member. The column has `streamId`
    (which cube) and `path` (which member).
  - **stored**: values kept in RevOS itself, typed in or written by actions.
    These need no stream.
  - **action**: runs an integration action per row and keeps the result.
- **Streams** list the cubes the table reads: `{ "id": "<cube name>" }` for
  the root, plus `joinPath`, the way to it from the root, for every other
  one. A stream holds nothing else: the cube itself knows where its data
  comes from.
- **Views** are layouts of the table. The default view also decides which
  rows show, through an attached segment or an ad-hoc filter.

You reach tables through the RevOS MCP server's generic tools:

| Call | What it does |
|---|---|
| `api_read { "resource": "tables", "params": { "fields": "id,name,updatedAt" } }` | list tables |
| `api_read { "resource": "tables", "id": "<table id>" }` | one table: `objectsColumns`, `streams`, `views`, `scoringFeatures` |
| `api_write { "resource": "tables", "data": { "name": "…" } }` | create (name only) |
| `api_write { "resource": "tables", "id": "<table id>", "data": { … } }` | update `name`, `objectsColumns`, `streams` |
| `api_read { "resource": "table-views", "method": "list", "id": "<TABLE id>" }` | the table's views |
| `api_write { "resource": "table-views", "id": "<VIEW id>", "data": { … } }` | update a view: `segmentId`, `filter`, `columns` |
| `api_delete { "resource": "tables", "id": "<table id>" }` | delete a table, for good (see *Deleting*) |

The record always goes under `data`. A body under any other key may be
ignored without an error. `api_details({ resource: "tables", operation:
"update" })` is the authority on the column and stream shapes. There is no
column endpoint: columns change through the table's `objectsColumns` array.

## The three things to keep in mind

**1. `objectsColumns` and `streams` are replaced whole.** An update stores
the array you send instead of the stored one:

- A column you leave out is removed from the table and from every view.
- `name` alone is a safe partial update.
- Sending `objectsColumns` without `streams` keeps the stored streams.
- A stream disappears by itself with the last column that read it (the root
  stays), so you rarely send `streams` except to add one.
- The server tidies what it stores: a path on the root is dropped, and a
  non-root stream sent without `joinPath` is stored as `<root>.<id>`. Read
  the table back to see what it kept.

**2. A table compiles into the org's semantic model.** RevOS generates a
Cube **view** per table from its streams and external columns. The server
doesn't check them on save. Any of these breaks every table, segment, and
query in the org until it's fixed:

- a stream `id` that isn't a cube;
- a `joinPath` hop that isn't a declared join;
- an external column whose `path` isn't a member of its stream's cube;
- an empty table name.

**3. One row per root record. A field from a "many" cube doesn't fit.**
Before you add a column from any cube other than the root, find out how
many of that cube each root record has. Look at the join between the two
cubes, from **both** sides, because it may be declared on either:

| join found | root has… | a dimension column from it |
|---|---|---|
| root → other: `many_to_one` or `one_to_one` | one | fine |
| other → root: `one_to_many` | one | fine |
| root → other: `one_to_many` | **many** | **don't add** |
| other → root: `many_to_one` (e.g. `crm_deals → crm_companies`) | **many** | **don't add** |

"Deal stage" on a companies table is the last row of that table: each
company has many deals, so there is no single stage to show, and the column
would repeat or scramble rows. **Don't add it, even as a caveat.** Stop and
tell the user why. Then offer what does fit:

- an aggregate from that cube as a measure column (`measure: true`): a
  count, a sum, or a filtered count such as "won deals", if the cube has
  one or one is added to it (the cubes skill);
- the same field on a table rooted on that cube (the Deals table);
- a filter on the rows through a segment ("companies with a won deal").

So every write follows the same loop:

1. **Read fresh** (`api_read` the table by id) right before writing. Keep
   the `objectsColumns` and `streams` you got. They are your undo.
2. **Write** the arrays with only your change applied.
3. **Verify at once**:
   - `api_read { "resource": "cubes", "method": "meta", "params": { "fields": "name", "pageSize": 100 } }`
     must succeed. An error means the org's model no longer compiles.
     Restore the saved arrays immediately, and then tell the user.
   - Query the table's view over the columns you touched:
     `api_read { "resource": "cubes", "method": "query", "body": { "query": { "dimensions": ["<view>.<column name>"], "limit": 3 } } }`.
     The view is named `model_<table id with - replaced by _>`, and its
     members are the column names. An error names the bad member.
4. **Read the table back** and check that the columns are what you meant.

## Reading a table

`get` the table and describe it in the user's terms:

- what one row is (the root cube);
- each column, with its display name, type, and where its value comes from
  (`cube.member`, stored in RevOS, or an action);
- which segment or filter scopes the default view (`views[].segmentId` /
  `filter`);
- whether the table is scored (`scoringFeatures`).

Don't dump the JSON. For the table's actual rows or aggregates, query its
view or the underlying cubes (see query-semantic-model).

## Creating and editing

Read the reference before writing:

- **New table**: [references/create.md](references/create.md)
- **Change a table** (add, change, remove, or hide columns; add a related
  cube; rename; scope its rows): [references/edit.md](references/edit.md)
- **Column and stream rules** (types, naming, `path`, `measure`, action
  columns, join paths): [references/columns.md](references/columns.md)

The cubes behind a table are a separate thing. If the member a column needs
doesn't exist yet, it has to be added to the cube first (the cubes skill).
Audiences are a separate thing too: build a segment with the segments skill,
then attach it here.

## Deleting

`api_delete` on `tables` removes the table for good. Nothing is soft
deleted, and there is no undo. It takes with it:

- the stored column values and the action results;
- the scores and the change history;
- the table's views and its view in the semantic model.

So never delete on an inference. Before the call:

1. Read the table and name it back to the user: what a row is, how many
   columns, which are stored or action columns, and whether it is scored.
2. Check what reads the table's cubes. Its view is `model_<id, - → _>` and
   its own cube, if it has stored columns or scores,
   `model_stream_<id, - → _>___local`. List the org's segments (full
   records: their `cubes` and `filter` aren't in `fields`) and tables
   (`fields: "id,name,streams"`), and look for either name. Anything that reads them stops compiling with the
   table gone, and takes the org's whole model down with it (rule 2). Report
   what you found; that has to be fixed first.
3. Say what goes with it (the list above), and ask for an explicit yes for
   **this** table. Approval to delete one table doesn't cover another.
4. Then `api_delete`, and confirm that `meta` still compiles and the table
   is gone from the `list`. The delete drops several stores in turn and
   isn't atomic: if it errors or times out, read the list before trying
   again, and tell the user what state the table is in.

The cubes and segments the table read stay, and so do the connected
systems: deleting a table writes nothing back to them. A table you created
yourself in a failed attempt is no exception: say so, and ask before
deleting it. A `403` means the user's role can't delete tables; someone
with a higher role in the organization has to do it.

## Reporting back

After a write, tell the user:

- what changed, in their terms ("added Industry, read from the company");
- that the model compiled and the view returned rows;
- any judgment call you made, such as the join path or the column type.

If you had to restore, say so plainly, along with the error.
