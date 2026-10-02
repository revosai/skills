# Deleting a cube

Deleting is permanent, and cubes have no version history to restore from.
Anything still pointing at the cube breaks, and some of those breaks take
down the whole org's semantic model. So this is mostly a check, and only
then a call.

## 1. Find it and keep a copy

`api_read { "resource": "cubes", "id": "<cube id>" }`. If you only know the
name, list with `filter: "name == \"…\""`. Keep the full stored record
(`name` + `definition`). If the user changes their mind, recreating from it
is the only way back. Offer to show it to them.

## 2. Check what depends on it

Run the full dependency check from SKILL.md (*Who depends on a cube*), then
act on what you find:

- **Tables** reading it (it appears in a table's `streams` or in a
  `joinPath`). **Don't delete.** The table's generated view would point at a
  missing cube, and the org's model would stop compiling. The table, or that
  stream on it, has to go first. That happens in RevOS, so tell the user.
- **Segments** with it in `cubes[].joinPath` or in filter members. **Don't
  delete** without the user's decision. Those segments fail on their next
  evaluation, and a table scoped by one can break too. The user should
  change or remove those segments first.
- **Other cubes** joining to it or referencing `${cube.…}`. Remove those
  joins and references first: edit each such cube with the full-definition
  update in edit.md, and verify that `meta` compiles. Only then delete.
  Otherwise the delete itself breaks compilation.
- **It's the org's only stored cube.** Say so. With no stored cubes the org
  has no semantic model to query. An org that once had a legacy model can
  fall back to it.

## 3. Confirm with the user

Name the cube and the table it reads, and list what you cleaned up or found
nothing in. Ask for an explicit yes, even if the tool will ask for approval
too. "Delete the old one" is not specific enough when two cubes read
similar tables.

## 4. Delete and verify

```json
api_delete { "resource": "cubes", "id": "<cube id>" }
```

Then confirm the model still compiles:

```json
api_read { "resource": "cubes", "method": "meta", "params": { "fields": "name", "pageSize": 100 } }
```

The cube should be gone and the call should succeed. If `meta` errors,
something still referenced the cube. Recreate it at once from the saved
record (`api_write` with `name` + `definition`). That gives it a new id, but
the name is what references use. Then find the reference you missed.

Report what was deleted, what was cleaned up beforehand, and that the model
compiles.
