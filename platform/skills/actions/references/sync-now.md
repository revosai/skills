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

## 1. The record and its source system

**The record id** is what the user gave, or the last path segment of the
link they pasted (a HubSpot deal link ends in `/record/0-3/<id>`). It is the
row's `objectId`.

**The source system** is the one the link or the user's words name:
HubSpot, Salesforce, Pipedrive. Ask only if neither says.

## 2. Sync the source

```json
api_read { "resource": "connections", "params": { "fields": "id,name,status,prefix" } }
```

Sync **every active connection of that system** — the ones whose `prefix`
or `name` carries its name (`hubspot_`, "HubSpot", "Hubspot Associations").
Not only the obviously named one: a record's own fields and its
associations — which company a deal belongs to — often arrive through
separate connections, and syncing one of them leaves the record pointing at
an association the warehouse hasn't caught up on.

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

Take each connection's usual duration from this same answer:
`lastSucceededAt` minus `lastSyncStartedAt`, when `lastSyncStatus` is
`"succeeded"`. Once your run finishes, those fields describe it instead.

If no active connection matches the system, don't pick one by guess. List
the active ones and ask.

## 3. Find the action column while the sync runs

**The record has run before** — its runs name the table and the column:

```json
api_read { "resource": "action-runs",
           "params": { "filter": "objectId == \"<record id>\"",
                       "orderBy": "createdAt desc", "pageSize": 5,
                       "fields": "id,actionId,columnId,modelId,objectName,status,createdAt" } }
```

`modelId` and `columnId` of the newest run are what to run. If the runs
span more than one column, name them and ask which one the user means,
unless the request already says ("to NetSuite").

**The record has no runs** — a new record, or one that was never in scope.
Then the table has to be found from the other side:

```json
api_read { "resource": "tables", "params": { "fields": "id,name,streams", "pageSize": 100 } }
```

Keep the tables whose **first** stream is this record type's cube (for a
HubSpot deal, `hubspot_deals`), read each, and keep those with a column of
type `action`.

- One table, one action column: that is the one.
- Several: don't choose. Name the candidates — table and column — and ask.
  Organizations split one record type across tables by rules of their own
  (a pipeline, a region, a test copy), and those rules are not in the API.
- None: say there is no action set up for this kind of record.

Whether the record is actually a row of the table you settled on, the run
itself will tell you (step 5).

## 4. Wait for the sync

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

## 5. Run the action for that one row

```json
api_write { "resource": "action-runs",
            "data": { "tableId": "<table id>", "columnId": "<action column id>",
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
