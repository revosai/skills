---
name: connections
description: >
  See, check, and sync RevOS connections — the pipelines that pull a source
  system (HubSpot, NetSuite, Salesforce) into RevOS's warehouse — through
  the RevOS MCP server. Use this whenever the user wants a source system
  synced into RevOS ("sync HubSpot", "refresh the NetSuite data", "pull the
  latest from the CRM"), asks whether data is up to date or when it last
  synced, asks which connections exist or what one syncs, or wants a
  connection or source deleted. Read it before the first api_write on
  `connections`, before an api_delete on `connections` or `sources`, and
  whenever another skill says to sync a connection. Pushing a row out to
  another system ("sync this deal to NetSuite") is an action: the `actions`
  skill.
---

# Connections

A **connection** pulls one source system's data into RevOS's warehouse
(through Airbyte), on a schedule: that is **ingestion**. Each one reads from
a **source** (the account and its credentials) and writes tables whose names
start with its `prefix`; the cubes over those tables usually carry the same
prefix (`hubspot_` → `hubspot_deals`).

The other direction, a row pushed from RevOS into another system, is
**activation**, done by actions: the `actions` skill. "Sync" can mean
either. Data coming **from** a system ("sync HubSpot", "refresh the data",
"is it up to date?") is this skill. A named record, or data going **to** a
system ("sync deal X", "push the deals to HubSpot"), is `actions`.

## Calls

| Call | What it does |
|---|---|
| `api_read { "resource": "connections", "params": { "fields": "id,name,status,prefix,sourceId" } }` | list them. Always with `fields` |
| `api_read { "resource": "connections", "id": "<connection id>" }` | one connection: `name`, `status`, `schedule`, `prefix`, `sourceId`, `streams` |
| `api_read { "resource": "connections", "id": "<connection id>", "method": "syncStatus" }` | is a job running, how the last sync ended, when data last landed |
| `api_write { "resource": "connections", "id": "<connection id>", "method": "sync" }` | start a sync now. No `data` |
| `api_read { "resource": "sources", "params": { "fields": "id,name,sourceType" } }` | the sources the connections read from. Never select `configuration`: it holds credentials |
| `api_read { "resource": "sources", "id": "<source id>" }` | one source |
| `api_delete { "resource": "connections", "id": "<connection id>" }` | delete a connection, see [Deleting](#deleting) |
| `api_delete { "resource": "sources", "id": "<source id>" }` | delete a source and every connection reading from it, see [Deleting](#deleting) |

The connection's id always goes in `id`, never in `data` or `params`.

`status` is `active`, `inactive` or `deprecated`. Only an active connection
syncs, on its schedule or when triggered.

A connection's `streams` (the objects it syncs: `deals`, `companies`, …)
and its `schedule` come only from reading it by id. Read one by id only when
the question is about those; a list answers everything else.

**Not possible here:** creating a connection, changing one (its schedule,
its streams, its status, so also activating an inactive one), and refresh,
reset or clear jobs. Say so; creating and changing connections is done in
the RevOS app. Don't look for another call.

## Which connections belong to a system

List the connections. A system's connections are those whose `prefix` or
`name` carries its name (`hubspot_`, "HubSpot", "Hubspot Associations").
Take **all the active** ones, not only the obviously named one: a record's
own fields and its associations (which company a deal belongs to) often
arrive through separate connections. Leave the inactive ones out, and
mention them in one line ("HubSpot (old) is inactive and doesn't sync").

If no prefix or name matches, list the sources and take the connections
whose `sourceId` is a source of that `sourceType`. If that finds none
either, don't guess: name the connections there are and ask.

A connection the user names that is inactive: don't trigger it. Say it is
inactive, that nothing ran, and that it is activated in the RevOS app.

## Reading syncStatus

- **`running`** — a job is in flight for the connection right now (a sync,
  or a refresh or reset, which blocks a sync too).
- **`lastSyncStatus`** — how the most recent sync run ended: `succeeded`,
  `failed`, `cancelled`, `incomplete`, or still `pending`/`queued`/`running`.
  `null` if none has run.
- **`lastSyncStartedAt`** — when that run started, whatever its outcome. Not
  a freshness marker on its own.
- **`lastSucceededAt`** with **`lastSucceededJobType`** — when a job last
  succeeded, and which kind. `"sync"` or `"refresh"` means fresh data
  landed. `"clear"` or `"reset"` means the tables were **emptied**, which
  the timestamp alone reads as "just synced".

**Usual duration:** `lastSucceededAt` minus `lastSyncStartedAt`, when
`lastSyncStatus` is `"succeeded"` and `lastSucceededJobType` is `"sync"`.
Take it before you trigger: the trigger's answer already describes the new
job. Otherwise there is no usual duration: say you don't know how long it
takes.

## Is our data up to date?

A question, not a request: read, trigger nothing. Take the system's active
connections, read each one's `syncStatus`, and report, in the user's words:

- when data last landed: `lastSucceededAt`, if `lastSucceededJobType` is
  `"sync"` or `"refresh"`; if it is `"clear"` or `"reset"`, that the tables
  were emptied and hold no fresh data;
- whether the latest sync failed: `lastSyncStatus` other than
  `"succeeded"`;
- whether one is running right now: `running`.

Then offer to sync. Don't start one unasked.

## Syncing a connection

1. For every connection to sync, read its `syncStatus` and note its usual
   duration.
2. Trigger every one of them:

   ```json
   api_write { "resource": "connections", "id": "<connection id>", "method": "sync" }
   ```

3. Read each answer:
   - **`started: true`** — your call started a run. Wait for it.
   - **`started: false`** — a job was already running, and your call did
     nothing. When `lastSyncStartedAt` is `null` here, the job isn't
     identified: follow it with `syncStatus`. Wait until `running` is
     `false`. That job started before you asked, so if the user said they
     just changed something at the source, or a record is waiting on this
     sync, trigger **once more** and wait for that run too. Once, not in a
     loop: if that answer is `started: false` again, wait for that job and
     don't trigger a third time. Otherwise the running job counts.
   - **409** — the connection isn't active. Nothing runs. Say so, and that
     it is activated in the RevOS app. Don't try to activate it.
4. Wait for all of them, as [Waiting](#waiting) says.

**Done** means `running` is `false`. If `lastSyncStatus` is `"succeeded"`,
the data is fresh. Anything else means it may still be stale: say so, with
that status.

## Waiting

Tell the user what you're waiting for and roughly how long it usually
takes. Then:

- If you can let time pass (a sleep in a shell tool), wait about the usual
  duration before the first check (with none, start at once), then 20–30
  seconds between checks.
- If you can't, check once. Still running: tell the user how long it
  usually takes and to ask you to check again. Don't poll in a loop: checks
  with no time between them all see the same answer.

## Deleting

`api_delete` on a connection stops its syncing for good; the data already
in the warehouse stays. It can't be undone. Delete only a connection the
user asked for by name: read it by id first, say which one it is (name,
prefix, source), and ask them to confirm before the call. Never delete one
to "fix" a failing sync.

Deleting a **source** goes further: it also removes the source's stored
credentials and every connection reading from it. Same rule, and name
those connections in the confirmation, from
`api_read { "resource": "connections", "params": { "filter": "sourceId == \"<source id>\"", "fields": "id,name,status,prefix" } }`.

You act with the user's own role, and both deletes need an organization
admin: for an admin they go through on the first call, so the confirmation
is the only check. If `api_delete` is refused (403), the user isn't an
admin: say an admin of the organization has to do it. Don't retry.

## Reporting back

Name connections by `name`, not id. Say which ones you synced, whether each
succeeded, and when the data last landed. For a failed sync, give
`lastSyncStatus`: these calls don't carry the reason, so don't make one up.
