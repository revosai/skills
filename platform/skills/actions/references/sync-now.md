# Syncing

"Sync" means two different things in RevOS, and the first job is to tell
which one the user wants:

- **Ingestion** pulls a source system's data (HubSpot, Salesforce,
  NetSuite) into RevOS through its **connections**.
- **Activation** pushes rows from RevOS into another system through an
  **action column**.

Decide by direction. Data coming **from** a system into RevOS ("sync
HubSpot", "refresh the data", "is it up to date?") is ingestion. Data going
**to** a system, or any named record ("sync deal X", "push this company",
"sync the deals to HubSpot"), is activation. If it is still unclear, ask.

## Ingestion: a source system

"Sync HubSpot" or "refresh the data": sync every active connection of that
system ([Syncing a connection](#syncing-a-connection)), wait for each, and
report which synced and whether they succeeded. "Is our HubSpot data up to
date?" is a question, not a request: read each connection's `syncStatus` and
report `lastSucceededAt` and `lastSyncStatus`. Don't trigger anything.

## Activation: one record, now

"Sync this deal", "push this company now", "force it through" — with a
record id or a link to the record in its source system.

Push a record RevOS already has straight away. Ingest its source first when
the record is missing, or when the user says they just changed it at the
source: RevOS's copy is then stale, and the action would send the old values
again, successfully.

This is not diagnosis. If the question is _why_ it failed, that is
SKILL.md's flow. Here the user wants it done, whether or not anything is
broken.

### 1. Is the record in RevOS?

**The record id** is what the user gave, or the last path segment of the
link they pasted (a HubSpot deal link ends in `/record/0-3/<id>`). It is the
row's `objectId`. **The source system** is the one the link or the user's
words name. Ask only if neither says.

Look the record up in the semantic model, not in `action-runs`. Its cube is
the source system's cube for that record type: for a HubSpot deal,
`hubspot_deals`. Pick it from the catalogue,
`api_read { "resource": "cubes", "method": "meta", "params": { "fields": "name,title,description", "pageSize": 1000 } }`
— the business cube, not an internal one (`[Table] …`, `[Segment] …`,
`model_stream_…___local`). Read its primary-key dimension, the one `meta`
marks `primaryKey: true`, from
`api_read { "resource": "cubes", "method": "meta", "params": { "filter": "name == \"<cube>\"" } }`.
Then one exact query:

```json
api_read { "resource": "cubes", "method": "query",
           "body": { "query": {
             "dimensions": ["<cube>.<primary key>"],
             "filters": [{ "member": "<cube>.<primary key>", "operator": "equals",
                           "values": ["<record id>"] }],
             "limit": 1 } } }
```

One row or none, go on to step 2. Don't retry with `contains`, another field
or another cube: an exact id that isn't there is the answer.

### 2. The table and its action column

```json
api_read { "resource": "tables", "params": { "fields": "id,name,streams,objectsColumns", "pageSize": 100 } }
```

Keep the tables whose **first** stream is the record's cube and that have a
column of type `action`. A table that holds its own rows has no root stream
and can't match.

- One table, one action column: that is the one.
- Several: unless the request already names the table or column, don't
  choose. Name the candidates — table and column — and ask. Organizations
  split one record type across tables by rules of their own (a pipeline, a
  region, a test copy), and those rules are not in the API.
- None: ask the user which table, or say there is no action set up for this
  kind of record. Only if the user can't name one either, as a last resort,
  read the record's newest runs, then name what you found and confirm it
  with the user before running. A run keeps the column it ran with, and that
  column may since have been replaced.

  ```json
  api_read { "resource": "action-runs",
             "params": { "filter": "objectId == \"<record id>\"",
                         "orderBy": "createdAt desc", "pageSize": 5,
                         "fields": "id,actionId,columnId,modelId,objectName,status,createdAt" } }
  ```

No table and column: stop here, and don't sync anything.

### 3. Ingest the source, only when needed

Only when step 1 found no row, or the user says they just changed the
record at the source ("I fixed the owner in HubSpot"). A bare "sync it",
"push it" or "force it" is not that: a record step 1 found goes straight to
step 4.

Sync the source system's connections as
[Syncing a connection](#syncing-a-connection) says, and wait until every
sync has succeeded. If step 1 found no row, run that same query once more:

- Still no row: say the record isn't in RevOS's data from that system under
  that id, and ask the user to check the id. Don't run the action.
- One row: go on.

### 4. Run the action for that one row

```json
api_write { "resource": "action-runs",
            "data": { "tableId": "<table id>", "columnId": "<action column id>",
                      "objectIds": ["<record id>"] } }
```

Always with `objectIds`. The rest is in [run.md](run.md): what comes back,
following the run by `parentId`, the refusals.

`rowsCount: 0` means the record is in RevOS but not a row of that table's
default view: it is outside the table's scope (its segment or filters), and
no sync changes that. Say so. Don't drop `objectIds` to force it through;
that runs the whole table.

## Syncing a connection

List the connections and take the system's **active** ones — those whose
`prefix` or `name` carries its name (`hubspot_`, "HubSpot", "Hubspot
Associations"):

```json
api_read { "resource": "connections", "params": { "fields": "id,name,status,prefix" } }
```

Sync every one of them, not only the obviously named one: a record's own
fields and its associations — which company a deal belongs to — often
arrive through separate connections, and syncing one of them leaves the
record pointing at an association the warehouse hasn't caught up on. If
none match, don't pick one by guess: list the active ones and ask.

For each one, take its usual duration **before** triggering, from
`api_read { "resource": "connections", "id": "<connection id>", "method": "syncStatus" }`:
`lastSucceededAt` minus `lastSyncStartedAt`, when `lastSyncStatus` is
`"succeeded"` and `lastSucceededJobType` is `"sync"`. The trigger's own
answer already describes the new job, so it can't tell you. Then trigger:

```json
api_write { "resource": "connections", "id": "<connection id>", "method": "sync" }
```

- **`started: true`** — your call started a run. It is the one to wait for.
- **`started: false`** — a job was already in flight, and yours did nothing.
  When `lastSyncStartedAt` is `null` in that answer, the job isn't
  identified: poll `syncStatus` until it ends. That run may predate the
  user's change (or the record's arrival): once it ends, trigger once more
  so a run that started _after_ the request exists. Once, not in a loop.
- **409** — the connection isn't active. Nothing runs. Say so and leave it;
  activating a connection is not part of this.

**Waiting.** Read `syncStatus` again:

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

## Reporting back

Whether the record was already in RevOS, which connections you synced (if
any) and that they succeeded, which table and action column ran for the
record, and how the run ended. If it failed, diagnose that run as SKILL.md
describes — the run, then its action's error instructions.
