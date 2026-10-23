---
name: connections
description: >
  See, check, and sync RevOS connections — the pipelines that pull a source
  system (HubSpot, NetSuite, Salesforce) into RevOS's warehouse — through the
  RevOS MCP server. Use this whenever the user wants a source system synced
  into RevOS ("sync HubSpot", "refresh the NetSuite data", "pull the latest
  from the CRM"), asks whether data is up to date or when it last synced,
  asks which connections exist or what one syncs, or wants a connection
  deleted. Read it before the first api_write or api_delete on
  `connections` or `sources`, and whenever another skill says to sync a
  connection. Pushing a row out to
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
| `api_read { "resource": "sources", "params": { "fields": "id,name,sourceType" } }` | the sources the connections read from |
| `api_delete { "resource": "connections", "id": "<connection id>" }` | delete a connection, see [Deleting](#deleting) |

The connection's id always goes in `id`, never in `data` or `params`.

`status` is `active`, `inactive` or `deprecated`. Only an active connection
syncs, on its schedule or when triggered.

A connection's `streams` (the objects it syncs: `deals`, `companies`, …)
and its `schedule` come only from reading it by id. Read one by id only when
the question is about those; a list answers everything else.

**Not possible here:** creating a connection, changing one (its schedule,
its streams, its status, so also activating an inactive one), and refresh,
reset or clear jobs. Say so, and that it is done in the RevOS app; don't
look for another call.

## Which connections belong to a system

List the connections. A system's connections are those whose `prefix` or
`name` carries its name (`hubspot_`, "HubSpot", "Hubspot Associations").
To sync, take **all the active** ones, not only the obviously named one: a
record's own fields and its associations (which company a deal belongs to)
often arrive through separate connections. Leave the inactive ones out, and
mention them only if the system has no active one.

If no prefix or name matches, list the sources and take the connections
whose `sourceId` is a source of that `sourceType`. If that finds none
either, don't guess: name the connections there are and ask.

## Is our data up to date?

A question, not a request: read, trigger nothing. For each of the system's
connections, read `syncStatus` and report, in the user's words:

- when data last landed: `lastSucceededAt`, if `lastSucceededJobType` is
  `"sync"` or `"refresh"`;
- whether the latest sync failed: `lastSyncStatus` other than
  `"succeeded"`;
- whether one is running right now: `running`;
- that it is inactive, if `status` isn't `active`: it doesn't sync on its
  own.

Then offer to sync. Don't start one unasked.

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
  landed. `"clear"` or `"reset"` means the tables are now **empty**, which
  the timestamp alone reads as "just synced".

**Usual duration:** `lastSucceededAt` minus `lastSyncStartedAt`, when
`lastSyncStatus` is `"succeeded"` and `lastSucceededJobType` is `"sync"`.
Take it before you trigger: the trigger's answer already describes the new
job.

## Syncing a connection

For each connection to sync:

1. Read its `syncStatus` and note the usual duration.
2. Trigger it:

   ```json
   api_write { "resource": "connections", "id": "<connection id>", "method": "sync" }
   ```

3. Read the answer:
   - **`started: true`** — your call started a run. Wait for it.
   - **`started: false`** — a job was already running, and your call did
     nothing. That job started before you asked, so it may miss the user's
     latest changes. Wait until `running` is `false` (when
     `lastSyncStartedAt` is `null` here, the job isn't identified, so poll
     `syncStatus` to follow it), then trigger **once more** and wait for
     that run. Once, not in a loop: if that answer is `started: false`
     again, wait for that job and don't trigger a third time.
   - **409** — the connection isn't active. Nothing runs. Say so, and that
     it is activated in the RevOS app. Don't try to activate it.

Trigger every connection of the system first, then wait for them together.

**When it's done:** `running` is `false`. If `lastSyncStatus` is
`"succeeded"`, the data is fresh. Anything else means the data may still be
stale: say so, with that status. Another skill waiting on this sync (the
`actions` skill's record sync) must stop there rather than act on data you
couldn't refresh.

## Waiting

Tell the user what you're waiting for and roughly how long it usually
takes. Then:

- If you can let time pass (a sleep in a shell tool), wait about the usual
  duration before the first check, then 20–30 seconds between checks.
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
credentials and every connection reading from it. Same rule, and name those
connections in the confirmation.

## Reporting back

Name connections by `name`, not id. Say which ones you synced, whether each
succeeded, and when the data last landed. For a failed sync, give
`lastSyncStatus`: these calls don't carry the reason, so don't make one up.
