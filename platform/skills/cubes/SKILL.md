---
name: cubes
description: >
  Read, create, edit, and delete the cube definitions behind an org's RevOS
  semantic model, through the RevOS MCP server. Use this whenever the user
  wants to change what the semantic model contains, even if they never say
  "cube": model a new table or source stream ("make HubSpot tickets
  queryable"), add or fix a dimension or measure ("add a revenue sum", "the
  close date should be a time field"), join two cubes ("link deals to
  companies"), rename or remove a field, delete a cube, see how a cube is
  defined ("show me the SQL behind crm_deals"), or find out why the semantic
  model or a table suddenly fails to load. Read it before any api_write or
  api_delete on the `cubes` resource. For answering business questions from
  the data, use query-semantic-model instead; for audiences, use segments.
---

# Cubes

A cube is one stored definition in the org's semantic model: which warehouse
table it reads (`sql_table`), the **dimensions** you group and filter by,
the **measures** you aggregate, and the **joins** to other cubes. Tables,
segments, and every semantic-model query are built on top of these.

You reach them through the RevOS MCP server's generic tools on the `cubes`
resource:

| Call | What it does |
|---|---|
| `api_read { "resource": "cubes", "params": { "fields": "id,name,updatedAt" } }` | list the stored definitions |
| `api_read { "resource": "cubes", "id": "<cube id>" }` | one stored definition, under `definition` |
| `api_read { "resource": "cubes", "method": "meta", "params": { "filter": "name == \"crm_deals\"" } }` | the **compiled** cube as the org can query it |
| `api_write { "resource": "cubes", "data": { "name", "definition" } }` | create |
| `api_write { "resource": "cubes", "id": "<cube id>", "data": { "definition" } }` | update |
| `api_delete { "resource": "cubes", "id": "<cube id>" }` | delete |

The record always goes under `data`. A body under any other key may be
ignored without an error. `api_details({ resource: "cubes", operation:
"create" })` is the authority on the definition's JSON schema.

## The one thing to keep in mind

**The server stores whatever you send, and Cube compiles all of the org's
cubes together.** A definition that doesn't compile doesn't fail on save.
It fails the *whole org's* semantic model: every table, segment, and query
errors until someone fixes it. Common causes are a join to a cube that
doesn't exist, a `${…}` reference to a member that isn't there, or a removed
dimension that a table column still uses. A wrong column name or bad SQL is
quieter: the model compiles, and only queries touching that member fail.

So every write follows the same loop:

1. **Keep the before-state.** For an edit, hold the full current
   `definition` you just read. For a create, remember the new id.
2. **Write.**
3. **Verify at once** with `meta` filtered to the cube's name. An error
   there means the org's model no longer compiles. **Restore immediately**:
   write the saved definition back, or delete the cube you just created.
   Then tell the user what happened, and don't keep editing on a broken
   model. If `meta` still shows the old version, wait a few seconds and read
   again; Cube polls for changes.
4. **Prove the SQL** with one small query over the members you added or
   changed:
   `api_read { "resource": "cubes", "method": "query", "body": { "query": { "dimensions": ["crm_deals.stage"], "measures": ["crm_deals.count"], "limit": 3 } } }`.
   An error here names the bad column or expression. Fix it the same way.

Writes need the **Developer** role. A 403 means the connected user doesn't
have it, so say so rather than retrying.

## Before the first write: two checks

**Is the org in cubes mode?** If the stored list is empty but `meta` returns
cubes, the org is still on the legacy, auto-generated model. Creating its
first stored cube switches the org to cubes mode, and every auto-generated
cube disappears with it. Don't create one. Tell the user it needs a
deliberate migration in RevOS instead.

**Are the cubes managed as code?** Some orgs ship cubes from a repo with the
RevOS CLI (`revos apply`). An edit made here is overwritten on their next
apply. If the user mentions a repo or the CLI, point them there instead.

## Reading

- **What's defined, and how**: list with `fields: "id,name,updatedAt"`, then
  `get` by id for the full `definition`. The list's `filter` is CEL on
  `name` (`name == "crm_deals"`, `name.startsWith("hubspot_")`).
- **What's actually queryable**: `meta`. It differs from the stored list:
  - It is compiled. Members are fully qualified, such as `crm_deals.amount`,
    and use camelCase keys.
  - It adds the cubes RevOS generates itself, which you never write:
    - a cube per table, named `model_stream_…___local`;
    - a cube per static segment, named `segment_…`;
    - a view per table.

When the user asks how a cube is defined, show the relevant part of the
stored definition: the table, the dimensions with their types, the measures,
and the joins. Explain it in plain words. Don't dump the JSON. To answer
questions *about the data*, switch to query-semantic-model.

## Who depends on a cube

Before you rename or remove anything, or delete a cube, find its users. Each
reference to the old name or member breaks:

- **Other cubes**: a `joins` key equal to this cube's name, or `${name.…}`
  in any join, dimension, or measure SQL. Get each stored definition and
  search it. Joins are declared on either side.
- **Tables**: list them with
  `api_read { "resource": "tables", "params": { "fields": "id,name,streams,objectsColumns" } }`.
  Each table has:
  - `streams[].id` (a cube name) and `streams[].joinPath` (dotted cube
    names);
  - `objectsColumns[]`, whose `streamId` + `path` point at a cube's
    dimension.
- **Segments**: list them, then `get` each by id. Each has
  `cubes[].joinPath` and the `member`s in its `filter`.

Report what you found to the user before acting: "crm_deals is used by the
Deals table (7 columns) and 2 segments".

## Creating, editing, deleting

Each has its own reference. Read the one you need before writing:

- **New cube**: [references/create.md](references/create.md)
- **Change a cube** (add or fix members, joins, rename): [references/edit.md](references/edit.md)
- **Delete a cube**: [references/delete.md](references/delete.md)
- **Definition syntax** (dimensions, measures, joins, SQL references):
  [references/definition.md](references/definition.md)

## Reporting back

After a write, tell the user in two or three sentences:

- what changed, in their terms ("added Amount as a sum measure on Deals");
- that `meta` compiled and a test query ran;
- any judgment call you made, such as a join's relationship or a dimension's
  type.

If you had to restore, say so plainly, along with the error that caused it.
