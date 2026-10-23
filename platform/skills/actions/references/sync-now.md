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

"Sync HubSpot", "refresh the data", "is our data up to date?": the
`connections` skill. Load it and follow it; nothing in this file applies.

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

Load the `connections` skill. Take the source system's connections as its
"Which connections belong to a system" section says, sync them as its
"Syncing a connection" section says, and wait until every sync has
succeeded. If one didn't, stop and say so: don't run the action on data you
couldn't refresh.

If step 1 found no row, run that same query once more:

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

## Reporting back

Whether the record was already in RevOS, which connections you synced (if
any) and that they succeeded, which table and action column ran for the
record, and how the run ended. If it failed, diagnose that run as SKILL.md
describes — the run, then its action's error instructions.
