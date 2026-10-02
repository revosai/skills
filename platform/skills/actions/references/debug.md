# Debugging a failed run beyond the run itself

Come here after SKILL.md's first level — you've read the run and its
`result` didn't settle the question. Two more levels, and the same rule:
**stop at the first one that answers.**

## Level 2 — the input and the mapping

Go here when the error is _about a value_: a field the target system calls
missing, empty or malformed, or an `input` that plainly isn't what the
action expects.

- `api_read { "resource": "tables", "id": "<the run's modelId>" }`. The
  column that ran is the one in `objectsColumns` whose `id` equals the run's
  `columnId`, and **its `config.input` is the mapping** the action was
  called with.
- Only when you can't tell what the action expects to be given:
  `api_read { "resource": "actions", "id": "<the run's actionId>" }` — its
  `description` says so.

Two things to read out of that mapping:

**Which columns feed the action.** Its values carry `{{columnId}}`
placeholders — `{{ col }}` and `{{col.property}}` both count, and the id is
the part before any dot. Those columns are the subject of the diagnosis;
the rest of `objectsColumns` is not, and a table can have dozens.

**Whether each value arrived.** Look each of those column ids up in the
run's `input`. Missing, `null` or `""` means the action was called without
it — which is upstream of both the action and the mapping, so it is the
explanation to reach for before proposing a mapping change. A placeholder
in the mapping with no matching key in `input` points at the mapping
instead.

## Level 3 — lineage

Go here only when a value is missing _and_ the user needs to know where it
should have come from.

A column whose `streamId` looks like `model_stream_<id>___local` takes its
value from **another table**, whose id is the captured `<id>` with every
`_` turned back into a `-`:
`model_stream_3f8e1c40_9a2b_4d77_bd51_6e0c2af9e413___local` is the table
`3f8e1c40-9a2b-4d77-bd51-6e0c2af9e413`. Any other `streamId` names a cube
the table reads directly.

That is what separates "the sync from the source system never populated
this" from "this table's own column is misconfigured" — two different
fixes, owned by two different people.

When the value comes from another table, check whether that table's own
action failed for the related record before concluding the data is simply
missing at the source: a deal can't sync because the company it points at
never got its id. List that table's failed runs (`modelId` is the source
table's id) and look for the related record by `objectName`. If it has
one, _that_ error is the root cause. Diagnose it as its own run: when it
belongs to a different action, read that action's `errorInstructions` and
use those, not this one's.

## Before you propose a fix

Check the recommendation against the organization's error instructions you
read with the run (SKILL.md). They may turn your obvious fix around.

## Where to land the blame

Three places, and the answer is always one of them:

1. **Upstream data.** A value the action needed was empty or stale at its
   source. The fix is in the source system or its sync — not in the action,
   and not in the column config. Say so plainly rather than proposing a
   mapping change that can't help.
2. **The configuration here.** The mapping references a column that carries
   the wrong thing, or nothing. The fix is in RevOS.
3. **The target system.** Dependencies populated, input sound, and the
   other side still refused. Quote `metadata.error.message` verbatim.

Say which of the three you landed on, and how deep you had to go to know.
"The HubSpot API rejected the email because it is already on another
contact" and "the email column is empty for this object" call for entirely
different actions from the user, and an answer that blurs them isn't an
answer.
