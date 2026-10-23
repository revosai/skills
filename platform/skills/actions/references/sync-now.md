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

### 1. The record, its action column, and whether RevOS has it

**The record id** is what the user gave, or the last path segment of the
link they pasted (a HubSpot deal link ends in `/record/0-3/<id>`). It is the
row's `objectId`. **The source system** is the one the link or the user's
words name. Ask only if neither says.

**The record has run before** — its runs name the table and the column:

```json
api_read { "resource": "action-runs",
           "params": { "filter": "objectId == \"<record id>\"",
                       "orderBy": "createdAt desc", "pageSize": 5,
                       "fields": "id,actionId,columnId,modelId,objectName,status,createdAt" } }
```

Run the `modelId` and `columnId` of the newest run. If the runs span more
than one column, name them and ask which one the user means, unless the
request already says ("to NetSuite"). A record with runs is a row of that
table, so it is in RevOS and needs no query: go to step 3. Exception: the
user says they just changed it at the source ("I fixed the owner in
HubSpot"). Then go to step 2 first. A bare "sync it", "push it" or "force
it" is not that.

**The record has no runs** — a new record, or one that was never in scope.
Find the table from the other side:

```json
api_read { "resource": "tables", "params": { "fields": "id,name,streams,objectsColumns", "pageSize": 100 } }
```

Keep the tables whose **first** stream is this record type's cube (for a
HubSpot deal, `hubspot_deals`) and that have a column of type `action`. A
table that holds its own rows has no root stream and can't match.

- One table, one action column: that is the one.
- Several: unless the request already names the table or column, don't
  choose. Name the candidates — table and column — and ask. Organizations
  split one record type across tables by rules of their own (a pipeline, a
  region, a test copy), and those rules are not in the API.
- None: say there is no action set up for this kind of record.

Then check that the record is in that cube. Take its primary-key dimension —
the one `meta` marks `primaryKey: true` — from
`api_read { "resource": "cubes", "method": "meta", "params": { "filter": "name == \"<cube>\"" } }`,
and run one exact query:

```json
api_read { "resource": "cubes", "method": "query",
           "body": { "query": {
             "dimensions": ["<cube>.<primary key>"],
             "filters": [{ "member": "<cube>.<primary key>", "operator": "equals",
                           "values": ["<record id>"] }],
             "limit": 1 } } }
```

One row: it is in RevOS. Go to step 3, or to step 2 first if the user just
changed it at the source. No rows: step 2. Don't retry with `contains`,
another field or another cube. An exact id that isn't there is the answer.

### 2. Ingest the source first

Sync the source system's connections as
[Syncing a connection](#syncing-a-connection) says, and wait until every
sync has succeeded.

If step 1 found no row, run that same query once more now:

- Still no row: say the record isn't in RevOS's data from that system under
  that id, and ask the user to check the id. Don't run the action.
- One row: go on.

If the record was already there and only stale, go straight to step 3.

### 3. Run the action for that one row

```json
api_write { "resource": "action-runs",
            "data": { "tableId": "<table id>", "columnId": "<action column id>",
                      "objectIds": ["<record id>"] } }
```

Always with `objectIds`. The rest is in [run.md](run.md): what comes back,
following the run by `parentId`, the refusals.

`rowsCount: 0` means the record is not a row of that table's default view:
outside its scope (segment or filters), or, for a record known only from
old runs, gone from the source. No sync changes that. Say so. Don't drop
`objectIds` to force it through; that runs the whole table.

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
