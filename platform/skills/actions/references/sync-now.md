# Syncing one record now

"Sync this deal", "push this company now", "force it through" — with a
record id or a link to the record in its source system. The user changed
something at the source and wants the action run on the fresh data.

Two things, and the order is the point: **pull the source first, then run
the action for that one row.** Run first and the action sends the stale
values again, successfully.

This is not diagnosis. If the question is _why_ it failed, that is
SKILL.md's flow. Here the user wants it done, whether or not anything is
broken.

## 1. Pin down the record and its action column

**The record id** is what the user gave, or the last path segment of the
link they pasted (a HubSpot deal link ends in `/record/0-3/<id>`). It is the
row's `objectId`.

**The action column** is the one this record has already run through. Its
runs say which:

```json
api_read { "resource": "action-runs",
           "params": { "filter": "objectId == \"<record id>\"",
                       "orderBy": "createdAt desc", "pageSize": 5,
                       "fields": "id,actionId,columnId,modelId,objectName,status,createdAt" } }
```

`modelId` and `columnId` of the newest run are the table and the action
column to run. If the runs span more than one column, name them and ask
which one the user means, unless the request already says ("to NetSuite").

No runs at all means the record has never run. Find the tables whose first
stream is this kind of record and which have a column of type `action`
(`api_read` on `tables`). If more than one could apply, ask the user which
table — a link to it is enough. Organizations split one record type across
several tables by rules of their own; don't guess between them.

## 2. Sync the source

Read the table (`api_read` on `tables`, the run's `modelId`). Its first
stream's `id` is the cube its rows come from — `hubspot_deals`. A connection
writes cubes named `<prefix><stream>`, so the connections of that source
system are the ones whose `prefix` starts that name:

```json
api_read { "resource": "connections", "params": { "fields": "id,name,status,prefix" } }
```

Sync **every active connection with that prefix**, not only the obviously
named one. A record's own fields and its associations — which company a
deal belongs to — often arrive through separate connections, and syncing
one of them leaves the record pointing at an association the warehouse
hasn't caught up on.

```json
api_write { "resource": "connections", "id": "<connection id>", "method": "sync" }
```

Read what comes back:

- **`started: true`** — your call started a run. It is the one to wait for.
- **`started: false`** — a job was already in flight, and yours did nothing.
  That run may predate the user's change: wait for it to end, then trigger
  again so a run that started _after_ the request exists.
- **409** — the connection isn't active. Nothing runs. Say so and leave it;
  activating a connection is not part of this.

Before moving on, take each connection's usual duration from this same
answer: `lastSucceededAt` minus `lastSyncStartedAt`, when `lastSyncStatus`
is `"succeeded"`. Once your run finishes, those fields describe it instead.

If no connection has a matching prefix, don't pick one by its name. Say you
can't tell which connection feeds this table, list the active ones, and ask.

## 3. Wait for it

```json
api_read { "resource": "connections", "id": "<connection id>", "method": "syncStatus" }
```

- **`running`** — any job in flight for the connection. Wait until `false`.
- **`lastSyncStatus`** — outcome of the most recent sync run. Anything but
  `"succeeded"` means the data may still be stale: say so and stop before
  the action, rather than running it on data you couldn't refresh.
- **`lastSucceededJobType`** — read it with `lastSucceededAt`. `"sync"` or
  `"refresh"` means fresh data landed; `"clear"` or `"reset"` means the
  tables are now empty, which a timestamp alone reads as "just synced".

Tell the user what you're waiting for and roughly how long it usually
takes. Then pace yourself:

- If you can let time pass (a sleep in a shell tool), wait about the usual
  duration before the first check, then 20–30 seconds between checks.
- If you can't, check once. Still running: tell the user how long it
  usually takes and that they should ask you to check again. Don't poll in
  a loop — checks with no time between them all see the same answer.

## 4. Run the action for that one row

```json
api_write { "resource": "action-runs",
            "data": { "tableId": "<modelId>", "columnId": "<columnId>",
                      "objectIds": ["<record id>"] } }
```

Always with `objectIds`. The rest is in [run.md](run.md): what comes back,
following the run by `parentId`, the refusals.

`rowsCount: 0` means the record is not a row of that table's default view:
it is outside the table's scope — its segment or filters — and no sync
changes that. Say so. Don't drop `objectIds` to force it through; that runs
the whole table.

## Reporting back

Which connections you synced and that they succeeded, which table and
action column ran for the record, and how the run ended. If it failed,
diagnose that run as SKILL.md describes — the run, then its action's error
instructions.
