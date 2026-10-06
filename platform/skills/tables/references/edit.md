# Editing a table

Column and stream rules are in [columns.md](columns.md). Every change below
goes through the write loop in SKILL.md:

1. Read fresh and keep the arrays.
2. Write with only your change applied.
3. Check that `meta` compiles and the view query works.
4. Read the table back.

## Send the array you read, with one change

`objectsColumns` is replaced whole. Start from the stored array, verbatim:

- keep every column's `id`, `name`, and settings;
- add, edit, or remove only what the user asked for;
- send the whole array back.

Build it from a fresh `get`, never from memory or an earlier turn. A column
you drop by accident is removed from the table and its views.

Copy only `objectsColumns` (and `streams` when you change them) into
`data`. A table read carries fields that no write accepts: `id`,
`organizationId`, `views`, `scoringFeatures`, `groups`, and timestamps.

## Add a column from the root cube

Append one column: `external: true`, `streamId` set to the root, `path`
set to the member, and the matching `type`. If the member is a measure,
add `measure: true`. No `streams` change is needed.

## Add a column from a related cube

For example: "add the company's industry to the deals table".

1. **First check how many of that cube each row has** (SKILL.md, rule 3).
   If the root has many, a dimension column doesn't fit, so stop here and
   offer a measure or another table instead.
2. Find the path from the root to that cube through declared joins
   (columns.md, *Streams*). Ask if there are two.
3. If the cube isn't in `streams` yet, append a stream: its `id` is the
   cube name, and its `joinPath` the path you found
   (`{ "id": "crm_companies", "joinPath": "crm_deals.crm_companies" }`).
   Send the full `streams` array, and keep the root first.
4. Append the column with `streamId` set to that cube.

## Change a column

- **Label**: change `displayName` and keep `name`. The name is what views,
  filters, and the view's Cube members use.
- **Source or type**: change `path`, `type`, or `measure` in place and keep
  the `id`. Check the new member against the cube first.
- **Hide, show, or reorder in a view**: that's the view's `columns`, not the
  table's. `api_read` the view, edit the one entry (`hidden`, `pinned`,
  `order`, `width`, `sort`), and send the view's whole `columns` array back
  with `api_write` on `table-views`.

## Remove a column

Before removing a column, check what refers to its `id`:

- **`scoringFeatures[].columnId`** on the table. If the column feeds the
  score, **don't remove it here.** An update leaves the scoring feature
  behind, pointing at nothing. The UI's column delete cleans that up, so
  send the user there.
- **View filters** (`filter` items with that `columnId`) in any of the
  table's views. Fix them, or ask the user.
- **Action columns** whose `config.input` uses `{{<that id>}}`.

Tell the user what you found. For a stored column, say that its values
become unreachable from the table. Then send `objectsColumns` without it.
If it was the last column reading a non-root stream, that stream goes
away by itself.

## Rename the table

`data: { "name": "…" }` alone is a safe partial update: trimmed, 1–255
characters, never blank.

## Scope, change, or unscope the rows

The default view decides which rows show:

1. `api_read { "resource": "table-views", "method": "list", "id": "<TABLE id>" }`,
   then take the entry with `isDefault: true`.
2. `api_write { "resource": "table-views", "id": "<VIEW id>", "data": { "segmentId": "<segment id>" } }`.
   Use `"segmentId": null` to show every row again.

The segment's root cube must be the table's root. If the user describes a
new audience, build the segment first with the segments skill.
