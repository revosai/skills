# Creating a cube

Syntax for every part of the definition is in [definition.md](definition.md).

## 1. Check that you can and should create it

- **Name is free.** Look for the name both among stored cubes
  (`params: { "filter": "name == \"crm_tickets\"" }`) and in `meta`. A
  clash doesn't error helpfully: a stored record of the same name is refused
  with a bare 500, and a `definition.name` that matches another cube, stored
  or generated, silently replaces or merges into it.
- **It isn't already modelled.** If a cube already reads the same
  `sql_table`, the user probably wants that cube edited, not a second copy.
  Ask.

## 2. Find the table

A cube reads one warehouse table. Data synced by a connection lands as
`<dataset>.<prefix><stream>`:

```json
api_read { "resource": "connections", "params": { "fields": "id,name,prefix" } }
api_read { "resource": "connections", "id": "<connection id>" }
```

`streams` can't be picked with `fields` (an unknown field is silently
ignored), so read the connection itself for them. Each connection carries its
`prefix`, and each stream its `name` and `primaryKey` (a list of paths, e.g.
`[["id"]]`). Take the dataset from an existing cube's `sql_table`, such as
`analytics.crm_companies` → `analytics`. When several connections or streams
could match the user's words, confirm which one before building.

## 3. Get the columns right

**No tool lists a warehouse table's columns.** Column names come from:

- the user;
- the stream's `primaryKey` and `cursorField` in the connection;
- other cubes over the same source, whose dimension SQL shows the source's
  naming style (`companyId` versus `company_id`).

Model what the user asked for, plus the primary key. Don't pad the cube with
guessed columns: every guess is a member that fails when queried. If you
don't know a column's exact name, ask, or model it and let step 6 prove it.

## 4. Build the definition

- `name` and `definition.name` must be the same. Use the source's naming
  (`crm_tickets`), not a sentence.
- Include:
  - a `title` and a one-line `description`;
  - `sql_table`, `data_source: "default"`, and the `refresh_key` pattern the
    other cubes use;
  - `meta.abConnectionId` and `meta.abStreamName` when it reads a stream.
- Include the primary-key dimension (`primary_key: true`, `public: true`) and
  a `count` measure, always.
- Pick each dimension's type: `time` for dates and timestamps, `number` for
  amounts, and `boolean` for flags.
- Add the measures the user wants, such as `sum`, `avg`, or a filtered
  `count`.
- **Joins.** Add one only when the user asks, or when the cube is plainly
  meant to connect to one already modelled (for example, a `company_id`
  column next to an existing `crm_companies` cube).
  - Check that the target cube exists and has the dimension you compare to.
  - Pick the relationship deliberately (definition.md, *Joins*).
  - A join declared on the *other* cube is an edit to that cube; see
    edit.md.

## 5. Write

```json
api_write { "resource": "cubes", "data": { "name": "crm_tickets", "definition": { "name": "crm_tickets", … } } }
```

Keep the returned `id`. It is your undo.

## 6. Verify

1. `meta` with `filter: "name == \"crm_tickets\""`. An error means the org's
   model no longer compiles (it reads only "failed with status 500").
   **Delete the cube at once**
   (`api_delete { "resource": "cubes", "id": "<new id>" }`), confirm `meta`
   works again, and then work out what was wrong.
2. Query every dimension you added plus `count`, with `limit: 3`. An error
   names the bad column. Fix it with an update (edit.md), or drop that
   dimension. Look at the rows: values that come back null where the user
   expects data usually mean a wrong column or type.
3. If you added a join, query one member from each side together. Then
   compare the joined `count` with the cube's own `count`. A jump means the
   relationship is wrong (fan-out).

## 7. Report

Tell the user:

- the cube's name and which table it reads;
- the dimensions and measures in plain words, and any join with its
  relationship;
- that it compiled and returned rows.

Mention that it's now available to tables, segments, and
semantic-model questions.
