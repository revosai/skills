---
name: create-connections
description: >
  Create a RevOS Connection YAML that syncs data from a Source into the
  org's data warehouse. Use whenever the user asks to: add a connection,
  set up a sync, ingest a table, pipe data from a source, configure streams,
  pick which tables to ingest, or wire up a Source. The skill picks a sensible stream subset
  (especially important for databases — most projects don't want every table)
  and confirms the choice before writing YAML.
---

# Create Connection

## Purpose

Author a `Connection` YAML under `connections/<name>.yaml` that ingests selected streams from a Source into the org's data warehouse. Each connection is a complete, standalone document — `revos apply` reads it and reconciles with the API.

The hard part is **stream selection** and **sync-mode choice**, not the YAML shape. Most sources expose far more streams than a project actually needs; databases especially. Pick deliberately, confirm with the user, then write.

---

## Prerequisites

- The Source already exists on the server (you'll get its `id` via `revos sources list`). If the user wants to ingest from a source that isn't created yet, stop and tell them to run `revos sources create` first — source configuration (connector picker, credentials, OAuth) lives in the RevOS UI. Once the user confirms they've returned from the UI, **re-run `revos connections list --json` and `revos sources list --json` before continuing** — the UI may have auto-created a connection for the new source. If a matching connection already exists, offer to pull it with `revos pull` rather than authoring a duplicate.
- `revos auth status` shows authenticated. If not, ask the user to run `revos auth login`.

---

## User Checkpoints

The skill makes two decisions that benefit from explicit confirmation. Don't skip them — wrong streams or wrong sync mode wastes warehouse storage and reload time.

### Checkpoint 1: Stream selection

After discovering streams and asking the user about their use case, propose a subset with one-line rationale per stream. Wait for confirmation or edits before moving on.

### Checkpoint 2: Sync-mode and key choices

After deriving sync mode + cursor + primary key for each selected stream, present the table and confirm before writing the file. Most users skim and approve; some will want to flip a stream to `full_refresh_overwrite` or change the cursor.

---

# Workflow

## Phase 1: Identify the Source

First, run `revos connections list --json` to see what connections already exist. If the user just returned from the web UI, this re-fetch is essential — the UI may have created a connection automatically. If you find a connection that matches the user's stated goal, surface it before proceeding so you don't create a duplicate.

Then run `revos sources list --json` and match on the server-side `name` (or run `revos sources list` for a scannable table). Record the source's `id` — that goes into the Connection YAML as `spec.source.id`.

If no source was named, ask the user which one. Don't proceed without an id.

## Phase 2: Discover streams

```bash
revos sources list-streams <id> --json
```

This returns an array of objects shaped like:

```json
{
  "streamName": "customers",
  "streamnamespace": "public",
  "syncModes": ["full_refresh_overwrite", "incremental_deduped_history", ...],
  "defaultCursorField": ["updated_at"],
  "sourceDefinedCursorField": false,
  "sourceDefinedPrimaryKey": [["id"]],
  "propertyFields": [["id"], ["email"], ["updated_at"], ...]
}
```

Save the full response — you'll reference it in later phases. The `syncModes` array narrows what's valid for this stream against the project's destination; never propose a mode that isn't in this list.

Two things worth knowing about the shape:

- **Database sources usually leave `defaultCursorField` empty** even when they advertise incremental modes. They expose every column via `propertyFields` and let you pick. Plan to fall back to `propertyFields` for DB sources; SaaS sources typically pre-fill `defaultCursorField` with the right field.
- **`streamnamespace` is set for databases** (e.g. `public`, `dbo`) and absent for most SaaS sources. The YAML needs the `namespace:` line whenever the discovery response includes one — drop the line for streams that don't have it.

## Phase 3: Ask about the use case

Before proposing streams, ask **one short question** to anchor the selection. Examples:

- "What do you want to analyze with this connection? E.g. revenue per customer, support ticket trends, marketing funnel."
- "Which part of the source matters here — sales pipeline, finance records, product usage?"

Keep it open-ended; one sentence from the user is enough. The goal is to filter out obviously-irrelevant streams (audit logs, internal queues, system tables) and prioritize business entities. Skip this question only if the user already stated the goal in their initial request.

## Phase 4: Propose a stream subset (Checkpoint 1)

Apply these rules in order:

1. **Drop technical/system streams** unless the user's goal explicitly needs them. Names matching any of: starts with `pg_`, `information_schema`, `_airbyte`, `temp_`, `tmp_`, `audit_`, `system_`, `migration`, `schema_migrations`; ends with `_history`, `_log`, `_audit`, `_archive`. Be conservative — when in doubt, include it and flag it.

2. **For databases** (postgres / mysql / mssql / mongodb-style sources, recognizable by many streams and namespaces like `public`, `dbo`, `sales`): expect to drop 30–80% of streams. Project use cases rarely need every operational table. Prefer streams whose names match the user's goal (`orders`, `customers`, `products` for revenue analysis; `tickets`, `contacts`, `messages` for support).

3. **For SaaS sources** (small flat stream list, no namespace, names like `companies`, `deals`, `tickets`, `engagements`): include all core business entities by default. Drop only obvious noise (`*_metadata`, `*_history`, `*_changelog`).

4. **Be honest about uncertainty.** If you can't tell what a stream is from its name, say so — don't fabricate a rationale.

Present the proposal as a table the user can scan:

```
Proposed streams (12 of 47):

  customers         core entity — revenue analysis needs this
  orders            transactions table; cursor: updated_at
  order_items       order line items; needed to break revenue by SKU
  products          dimension table for orders/order_items
  ...

Dropped (35): pg_stat_*, _airbyte_internal_*, audit_*, schema_migrations,
              user_sessions (not in scope for revenue analysis), ...
```

Ask: "Look right? Anything to add or remove?" Wait for the user. They might say "add `users`" or "drop `products`, we don't need it" — adjust.

## Phase 5: Determine sync mode, cursor, and primary key per stream

For each selected stream, the choice is driven by what the source supports (`syncModes`) and what fields it advertises. The four sync modes you'll use:

| Sync mode                        | Requires                   | When to use                                                                                                                       |
| -------------------------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `incremental_deduped_history`    | cursor **and** primary key | Best default. Source advertises a cursor (e.g. `updated_at`) and a PK. Only new/changed rows pull; duplicates collapse on PK.     |
| `incremental_append`             | cursor only                | Source has a cursor but no PK (event streams, append-only logs). Rows accumulate; no deduplication.                               |
| `full_refresh_overwrite_deduped` | primary key only           | Source has a PK but no usable cursor. Each sync replaces the destination table, deduplicated by PK. Fine for small/medium tables. |
| `full_refresh_overwrite`         | nothing                    | Small dimension tables (<10k rows), or when nothing else works. Each sync overwrites.                                             |

Decision algorithm per stream:

1. Pick the **strongest mode the source supports**, in this priority order: `incremental_deduped_history` → `incremental_append` → `full_refresh_overwrite_deduped` → `full_refresh_overwrite`. Skip any mode not in the stream's `syncModes` array.
2. For modes requiring a cursor: use `defaultCursorField` if non-empty. Otherwise look at `propertyFields` for the first available timestamp-looking field (`updated_at`, `modified_at`, `last_modified`, `_updated`, `timestamp`). If nothing fits, drop down to a full-refresh mode.
3. For modes requiring a primary key: use `sourceDefinedPrimaryKey` if non-empty. Otherwise look in `propertyFields` for an `id`-like field (`id`, `<entity>_id`, `uuid`, `key`). If nothing fits, drop down to `incremental_append` or `full_refresh_overwrite`.

Use compact notation when presenting (Checkpoint 2):

```
Stream             Sync mode                       Cursor        Primary key
customers          incremental_deduped_history     updated_at    id
orders             incremental_deduped_history     updated_at    id
order_items        incremental_append              created_at    —
products           full_refresh_overwrite          —             —
```

Ask: "Sync modes look right? Any changes?" Common edits: dropping a large table to `full_refresh_overwrite` only if it's small/static; switching cursor field.

## Phase 6: Write the YAML

Two names to pick, with different rules:

- **`metadata.name`** — the local IaC slug. Filename-friendly: lowercase, alphanumerics + hyphens. Anchors the YAML file (`connections/<metadata.name>.yaml`) and how other resources refer to this connection. Derive from the source and scope: `hubspot-sales`, `postgres-prod-revenue`, `stripe-billing`.
- **`spec.name`** — the human-readable label shown in the RevOS UI. Short, sentence case, spaces fine, no underscores. Describe what the connection syncs so a teammate scanning the UI knows without opening it. Patterns that work: `"HubSpot sales pipeline"`, `"Postgres prod → revenue tables"`, `"Stripe billing & subscriptions"`. Avoid reusing the slug here — `hubspot-sales` is a worse `spec.name` than `HubSpot sales pipeline`.

If a file already exists at the target path, ask whether to overwrite or pick a different name.

Template:

```yaml
apiVersion: revos/v1
kind: Connection
metadata:
  name: hubspot-sales
spec:
  name: HubSpot sales pipeline
  source: { id: <id from `revos sources list`> }
  schedule: { units: 24, timeUnit: hours }
  status: active
  streams:
    - name: customers
      namespace: public # omit if the stream has no namespace
      syncMode: incremental_deduped_history
      cursorField: [updated_at]
      primaryKey: [[id]]
```

Notes:

- `source.id` is the server id of the Source (e.g. `src_abc123`). Sources are not IaC — get the id with `revos sources list`.
- `primaryKey` is a list of lists — each inner list is one PK column path, supporting nested keys. Most cases it's `[[id]]`.
- `cursorField` is a flat list of path segments. Top-level field is `[updated_at]`; nested would be `[meta, modified_at]`.
- Omit `cursorField` and `primaryKey` for `full_refresh_overwrite`. Omit only `cursorField` for `full_refresh_overwrite_deduped`. CLI validation rejects missing required fields at apply time, so keep this clean.
- Don't set `metadata.id` or `spec.prefix` — both are filled in by `revos apply` on first create.

**Stream mappers** (`streams[].mappers`) are server-side transformations applied before rows land in BigQuery — hashing PII, renaming columns, dropping fields, filtering rows, encrypting values. Default to a clean sync without them. Load [references/mappers.md](references/mappers.md) when either:

- The user mentions masking, hashing, PII, renaming, dropping a column, filtering rows, or encryption.
- A selected stream's `propertyFields` includes obviously sensitive columns (`email`, `phone`, `ssn`, `ip_address`, full-name pairs, payment fields). In that case load the reference, then proactively suggest a mapper with the field name and rationale, and ask the user to confirm before adding it. Don't quietly insert mappers — masking the wrong field corrupts analysis.

## Phase 7: Validate locally

```bash
revos diff
```

The CLI parses the YAML through zod and reports what would change. Look for:

- **Parse errors** — schema rejections (missing required fields, invalid sync mode). Fix and re-run.
- **Drift report** — the new connection should appear as a single `create` entry.

If `revos diff` is clean, hand back: "Connection YAML written to `connections/<slug>.yaml` and validated. Run `revos apply` to create it on the server."

If validation fails, share the error verbatim and fix before declaring success.

---

# Common pitfalls

- **Picking a sync mode the source doesn't support.** Always intersect your choice with the stream's `syncModes` array from Phase 2. The API validates this server-side; better to catch it locally.
- **Using a source name where the server id is expected.** `spec.source.id` is the server id (e.g. `src_abc123`), not a display name or a slug. Always pull it from `revos sources list`.
- **Setting `cursorField` on a `full_refresh_*` mode.** CLI validation tolerates extra fields but it's noise. Omit fields that don't apply to the chosen mode.
- **Proposing every stream.** Especially for databases. If the user says "all of them" after seeing the proposal, fine — but offer the curated list first.
- **Inventing fields.** Only use `cursorField` and `primaryKey` values that appear in the discovery response (`defaultCursorField`, `sourceDefinedPrimaryKey`, or `propertyFields`).
