# Running an action column

```json
api_write { "resource": "action-runs",
            "data": { "tableId": "<table id>", "columnId": "<action column id>",
                      "objectIds": ["<row id>", "…"] } }
```

This queues one run per row and returns at once. **It acts on connected
systems** — records get created and updated in the customer's CRM or ERP,
and that can't be taken back from here. Only run when the user asked for
it, and be sure of the scope before you do.

## Scope: which rows

- With `objectIds` (1 to 1000 of them): only those rows.
- **Without `objectIds`: every row in the table's default view.** That is
  the whole table, or the segment attached to its default view — possibly
  thousands of writes to another system. Never leave `objectIds` out
  because you didn't know which rows were meant; ask. When the user does
  mean all of them, say that it covers every row in the default view — and
  how many that is when you can tell, e.g. the attached segment's
  `objectCount` — and get a yes before you run.

An object id is the row's `id` in the table — the same value a run carries
as `objectId`. For a row you know only by name, query the table's view for
its `id` (the tables skill explains the view).

`columnId` is the action column's `id` in the table's `objectsColumns`, not
its name. A column that isn't of type `action` is answered with "Table or
column not found", the same as a wrong id.

## Re-running a failed run

Take all three from the run itself:

```json
api_write { "resource": "action-runs",
            "data": { "tableId": "<run.modelId>", "columnId": "<run.columnId>",
                      "objectIds": ["<run.objectId>"] } }
```

Don't re-run unchanged when the run's `error.isUnrecoverable` is `true`, or
when the cause was a missing or wrong value that nobody has fixed yet — it
fails the same way. A value fixed in the source system reaches RevOS only
with that source's next sync, so a re-run straight after the fix can still
see the old value — to pull the source first and then run, follow
[sync-now.md](sync-now.md).

## What comes back, and following it

`{ "parentId": "…", "rowsCount": 12 }`. `rowsCount` is how many rows were
queued; `parentId` is shared by every run this request started and is
absent when nothing ran (`rowsCount: 0` — no row matched, so check the
ids before trying again).

The runs themselves take time. Follow them with:

```json
api_read { "resource": "action-runs",
           "params": { "filter": "parentId == \"<parentId>\"",
                       "fields": "id,objectName,status,attemptsMade" } }
```

`ACTIVE`, `WAITING` and `DELAYED` are still in progress (`DELAYED` is
usually a retry backing off); `COMPLETED` and `FAILED` are final. Report
the counts, and for failures go back to SKILL.md's first level with each
failed run's id.

## Refusals

- **403, "not allowed for "Startup" plan"** — running actions needs a paid
  plan. Tell the user; there is nothing to retry.
- **429** — runs can be started at most once every half second per
  organization. Wait and send the request again; don't split one run into
  many small requests.
- **404, "Table or column not found"** — a wrong `tableId`, a wrong
  `columnId`, or a column that isn't an action column.
