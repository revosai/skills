# Creating a table

Column and stream rules are in [columns.md](columns.md).

## 1. Decide what one row is

The root cube is the rows: "a table of our companies" is rooted on the
companies cube, and "a table of deals" on the deals cube. Read the
catalogue:

```json
api_read { "resource": "cubes", "method": "meta", "params": { "fields": "name,title,description", "pageSize": 100 } }
```

Then read the root's full definition, both compiled and stored:

- `meta` filtered to the cube gives the member names and types.
- `get` on the stored cube gives `meta.abConnectionId`, `abStreamName`,
  and `nameDimension`.

From those, note the root's primary-key dimension and its name dimension.
Prefer business-named cubes over generated ones (`model_…`, `segment_…`).
Ask when the user's words fit two cubes.

**If the table should hold only some rows** ("the stalled deals"), the rows
are scoped by a segment, not by the table:

1. Build the segment first with the segments skill, rooted on the same cube.
2. Create the table.
3. Attach the segment in step 5.

## 2. Check for a namesake

`api_read { "resource": "tables", "params": { "filter": "name == \"…\"", "fields": "id,name" } }`.
Tables can't be deleted from here, so a duplicate is clutter the user has
to remove in the UI.

## 3. Create it with the name only

```json
api_write { "resource": "tables", "data": { "name": "Companies" } }
```

The create body takes **only** `name`, which is trimmed and must be 1–255
characters. Anything else is rejected. Take the `id` from the response. The
table now exists, with a default view and no columns. Tell the user up
front that building it takes several writes.

## 4. Add the root stream and the columns

One update carries `streams` with the root, and `objectsColumns`:

- the `id` column, from the root's primary key;
- the `name` column, from the name dimension if there is one, with `id`
  then hidden;
- the columns the user asked for.

```json
api_write { "resource": "tables", "id": "<table id>", "data": {
  "streams": [ { "id": "crm_companies", "connectionId": "<abConnectionId>", "streamName": "companies" } ],
  "objectsColumns": [
    { "name": "id", "type": "string", "external": true, "streamId": "crm_companies", "path": "id", "hidden": true },
    { "name": "name", "displayName": "Name", "type": "string", "external": true, "streamId": "crm_companies", "path": "name" },
    { "name": "industry", "displayName": "Industry", "type": "string", "external": true, "streamId": "crm_companies", "path": "industry" }
  ] } }
```

Columns from a related cube need that cube as a stream, with a `joinPath`
when it isn't directly `<root>.<cube>` (see columns.md). Watch for fan-out:
a "many" cube's fields go in as measures. If the user hasn't decided on
more columns, stop at `id` and `name`. Don't invent columns.

## 5. Scope the rows (only if there's a segment)

1. `api_read { "resource": "table-views", "method": "list", "id": "<TABLE id>" }`,
   then take the entry with `isDefault: true`.
2. `api_write { "resource": "table-views", "id": "<that VIEW's id>", "data": { "segmentId": "<segment id>" } }`.

The segment's root cube must be the table's root cube. A view holds a
segment or its own `filter`, never both. A STATIC segment that isn't
`READY` scopes nothing yet, so warn the user.

## 6. Verify and report

Run the verify loop from SKILL.md:

- `meta` compiles;
- a 3-row query on the view (`model_<table id, - → _>`) over the new
  columns succeeds;
- reading the table back shows the columns and the stream you meant.

Then tell the user:

- what a row is;
- the columns and where each comes from;
- which segment scopes the table, if any;
- that it's ready in RevOS.
