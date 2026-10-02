---
name: actions
description: >
  Inspect, run, and debug RevOS actions — the operations an integration
  performs per table row (sync a company to NetSuite, enrich a contact, push
  a deal to HubSpot) — and their runs, through the RevOS MCP server. Use this
  whenever something failed, did not sync, or came out wrong ("why didn't
  this deal reach NetSuite?", "the sync is red", "what does this error
  mean?"), when the user wants to see which actions exist or what an action
  column did, or wants an action run or re-run for some or all rows — even
  if they never say the word "action". Read it before the first api_read or
  api_write on the `action-runs` resource.
---

# Actions

Three things share the name, and telling them apart is most of the work:

- An **action** is one operation of an integration against one object:
  "NetSuite upsert customer", "Enrich name". The catalogue is the `actions`
  resource; each has an `id` and an `integrationName`.
- An **action column** is an action wired into a table: which action, its
  `params`, and the `input` mapping that says which of the row's columns
  feed it. It lives in the table's `objectsColumns` (the tables skill covers
  adding and changing one).
- An **action run** is one execution of one action column against one row.
  Its status is one of `ACTIVE`, `DELAYED`, `WAITING`, `COMPLETED`,
  `FAILED`. Runs are kept for 14 days.

You reach them through the RevOS MCP server's generic tools:

| Call | What it does |
|---|---|
| `api_read { "resource": "actions", "params": { "fields": "id,name,integrationName" } }` | the catalogue; add `"onlyUsed": "true"` for the ones a table uses |
| `api_read { "resource": "actions", "id": "<action id>" }` | one action: `name`, `description`, `integrationName` |
| `api_read { "resource": "actions", "id": "<action id>", "method": "errorInstructions" }` | what this organization wrote about that action's errors |
| `api_read { "resource": "action-runs", "params": { … } }` | list runs: `filter`, `orderBy`, `fields`, `pageSize` |
| `api_read { "resource": "action-runs", "id": "<run id>" }` | one run, with its `input` and `result` |
| `api_write { "resource": "action-runs", "data": { "tableId": "…", "columnId": "…" } }` | run an action column — see [references/run.md](references/run.md) first |

`api_details({ resource: "action-runs" })` is the authority on the filter
and field names; this skill covers what that schema can't tell you.

## Something failed: start from the run

Most questions here are "why did this fail". Work in levels and **stop at
the first one that answers the question**: a failure whose cause is already
named in the run's own result doesn't need the table's schema, and pulling
it anyway costs the user a slower answer buried in detail they didn't ask
for.

**Find the run.** The user may hand you a run id straight from the
action-run drawer in the UI. Otherwise list, without the payloads:

```json
api_read { "resource": "action-runs",
           "params": { "filter": "status == \"FAILED\" && modelId == \"<table id>\"",
                       "orderBy": "createdAt desc", "pageSize": 10,
                       "fields": "id,actionId,columnId,modelId,objectId,objectName,status,attemptsMade,createdAt" } }
```

`modelId` is the table's id. Narrow with `columnId` or `objectId` when you
know them.

**Read the run** by id. One call, and it carries the spine as well as both
payloads: `actionId`, `columnId`, `modelId`, `objectId`, `objectName`,
`status`, `attemptsMade`, `input` and `result`.

**Read the organization's error instructions** for the run's `actionId`,
right after the run: one more call, described
[below](#the-organizations-error-instructions). They often map the error
message straight to its cause and fix.

**Where the error lives.** There is no separate error column. `result`
holds the whole run result, a union discriminated by `metadata.success`. On
a failure it carries:

- `metadata.error.message` — the message to trust and to quote;
- `metadata.error.aiMessage` — a generated rewording, present only if the
  explain-error flow ran. Never present it as the system's own error;
- `error` — a normalized object with `message`, `code`, `details`,
  `isUnrecoverable` and `retryAfter`.

`error.isUnrecoverable: true` means the framework deliberately stopped
retrying: the condition is permanent (rejected credentials, a validation
the target system will never accept), so suggesting a re-run unchanged is
wrong.

A large share of failures are fully explained right here — credentials the
target system rejected, a rate limit, a permission, a validation message
that already names the field and the reason. When `result`, read together
with the organization's instructions, says something the user can act on,
**that is the answer**: quote it, say what to do, stop.

**When the id doesn't resolve.** A table cell goes on showing a failure
long after the run behind it was removed, so an id can name a run older
than the 14-day window. Say so and stop — no page of `action-runs` can
contain it. If the user quoted the error text, that text is still worth
reading back to them. Then offer what does work: re-run the action and
diagnose the fresh failure.

**When the run alone doesn't answer** — the error is about a value that was
missing, empty or malformed, or the user asks where a value should have
come from — go on to [references/debug.md](references/debug.md): the
mapping, the lineage, and how to say where the fault is.

## The organization's error instructions

Organizations write down what their actions' errors mean and how they are
fixed: what a particular NetSuite error really means for them, who fixes
what, how a link to their CRM is built. Read them once for each failed run
you diagnose, by the run's `actionId`:

```json
api_read { "resource": "actions", "id": "<the run's actionId>", "method": "errorInstructions" }
```

It returns three texts, each `null` when nothing was written:

- `global` — applies to every action in this organization;
- `integration` — every action of this action's integration;
- `action` — this action alone.

They add up rather than override one another: the action-level text
assumes you've read the integration-level one.

They are where a convention that makes your obvious recommendation wrong
lives. When they give wording, a link format, or an owner for the fix, use
theirs. If all three are `null`, the organization wrote nothing for this
action; carry on without them. If the read itself is refused, don't retry:
carry on from the run, and say you couldn't read them.

## Running an action

Running acts on connected systems — it creates and updates records in the
customer's CRM or ERP — so only do it when the user asks, and read
[references/run.md](references/run.md) before the first `api_write` on
`action-runs`.

## Adding or changing an action column

That is a change to the table, not to the action: the tables skill, its
column reference. The catalogue here tells you which `actionId` to use and,
through the action's `description`, what input it expects.

## Reporting back

Lead with the cause in the user's terms, then what to do about it and who
does it. Quote `metadata.error.message` verbatim when the fix involves a
third party — a paraphrased vendor error is worse than useless when the
user takes it to that vendor's support. Name the row by `objectName`, not
by id. Don't dump `input` or `result`.
