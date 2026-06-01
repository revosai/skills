# Stream mappers

Stream mappers are **server-side transformations** applied per stream before rows land in BigQuery. They run inside the sync pipeline, so even a direct BigQuery query sees only the transformed values — no way for downstream analysts to bypass them.

Five mapper types are supported. They're all opt-in: a clean sync needs none of them. Add them only when the user asks for masking, renaming, dropping, filtering, or encryption.

| Type              | Use when                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------- |
| `hashing`         | One-way obfuscation of PII (email, name, IP). Analysts get a joinable but irreversible identifier.                  |
| `field-renaming`  | Rename a column at ingest. Useful when the source field name leaks sensitivity (`ssn` → `ssn_redacted`).            |
| `field-filtering` | Drop a column entirely. Use when the value should never reach the warehouse (notes, internal flags, free-text PII). |
| `row-filtering`   | Drop entire rows that match a predicate. Use to exclude test/demo data, soft-deleted rows, internal accounts.       |
| `encryption`      | Reversible obfuscation. Use when a process downstream of BigQuery needs to recover the plaintext.                   |

Mappers live under `streams[].mappers` as an ordered list. The configuration body always sits under `mapperConfiguration` — that's the schema shape, not a stylistic choice.

---

## When to proactively suggest a mapper

The skill should propose a mapper without being asked when the stream's `propertyFields` includes anything obviously sensitive:

- **Hash, don't store plaintext**: `email`, `email_address`, `phone`, `phone_number`, `ip_address`, `ssn`, `tax_id`, `national_id`, `passport`, `dob`, `date_of_birth`, `full_name`, `first_name + last_name` pairs.
- **Drop entirely**: free-text fields whose names hint at user-entered content (`notes`, `comments`, `internal_notes`, `description`) — unless the user said they need them for analysis.
- **Encrypt (reversible)**: payment-method fields (`card_number`, `iban`, `account_number`) when the user has indicated a downstream process needs the original values.

When suggesting, name the field and the mapper type, explain why, and ask the user to confirm or skip. Never quietly insert a mapper the user didn't approve — masking the wrong field corrupts analysis. Be especially conservative for `encryption`: a missing `key` value makes the YAML pass schema validation but the sync fails at runtime.

---

## Hashing

One-way hash that preserves joinability (the same input always produces the same hash). Default to `SHA-256` — it's the safest choice unless the user has a reason to prefer something else.

```yaml
streams:
  - name: customers
    namespace: public
    syncMode: incremental_deduped_history
    cursorField: [updated_at]
    primaryKey: [[id]]
    mappers:
      - type: hashing
        mapperConfiguration:
          targetField: email
          method: SHA-256
          fieldNameSuffix: _hashed
```

- `targetField`: the source column to hash. Must match a field in `propertyFields`.
- `method`: one of `MD2`, `MD5`, `SHA-1`, `SHA-224`, `SHA-256`, `SHA-384`, `SHA-512`. MD5/SHA-1 are weak — only use them if the user explicitly asks (e.g. matching an existing hashed dataset).
- `fieldNameSuffix`: appended to the column name in the destination. So `email` becomes `email_hashed` in BigQuery. Omit if the user wants to replace the column in place — but suffix is the safer default since it makes the transformation visible.

---

## Field renaming

Rename a column on its way into the warehouse. Use when the source name itself is sensitive (column called `ssn` becomes `ssn_redacted` after a separate hashing/filtering step) or when the source uses awkward names you want analysts to see clean.

```yaml
mappers:
  - type: field-renaming
    mapperConfiguration:
      originalFieldName: ssn
      newFieldName: ssn_redacted
```

Rename runs after hashing — chain them when you want both: hash to `ssn_hashed`, then rename if needed.

---

## Field filtering

Drop a column entirely from the destination table. The value never lands in BigQuery.

```yaml
mappers:
  - type: field-filtering
    mapperConfiguration:
      targetField: internal_notes
```

Prefer this over hashing when the value has no analytical use — there's no reason to store a hashed `internal_notes` column when you can just drop it.

---

## Row filtering

Drop rows that match a predicate. Use to exclude test data, soft-deleted records, internal accounts, etc.

The `conditions` tree uses nested boolean operators (`AND`, `OR`, `NOT`) and leaf comparisons (`EQUAL`, `NOT_EQUAL`, others). **The predicate keeps rows where it evaluates to true** — so to drop rows, wrap the match condition in `NOT`.

```yaml
mappers:
  # Keep rows where is_test != "true". Test rows get dropped.
  - type: row-filtering
    mapperConfiguration:
      conditions:
        type: NOT
        conditions:
          - type: EQUAL
            fieldName: is_test
            comparisonValue: "true"
```

Gotchas:

- **Compare against real sentinel values**, not empty strings or nulls — empty-string comparisons behave unreliably across source connectors.
- **Boolean fields**: most sources serialize booleans as strings on the wire, so the `comparisonValue` is `"true"` / `"false"`, not `true` / `false`. Confirm against `propertyFields` if unsure.
- **The keep-vs-drop direction is easy to flip.** Re-read the predicate after writing it: "this filter keeps rows where **_, so it drops rows where _**."

---

## Encryption

Reversible obfuscation. Use only when a process downstream of BigQuery genuinely needs to recover the plaintext — otherwise prefer hashing or filtering.

```yaml
mappers:
  - type: encryption
    mapperConfiguration:
      algorithm: AES
      targetField: card_number
      fieldNameSuffix: _enc
      key: ${env.AES_KEY}
      mode: GCM
      padding: NoPadding
```

- `algorithm`: `RSA` or `AES`.
- `mode` (AES only): `CBC`, `CFB`, `OFB`, `CTR`, `GCM`, `ECB`. Default to `GCM` — it's authenticated and resistant to tampering. Only fall back to others if the user has a stated reason.
- `padding` (AES only): `NoPadding` or `PKCS5Padding`. With `GCM`/`CTR`/`CFB`/`OFB`, use `NoPadding`. With `CBC`/`ECB`, use `PKCS5Padding`.
- `key`: the encryption key. Reference an environment variable with `${env.VAR_NAME}` — never hardcode the key in YAML. Tell the user they need to set the env var in the project's deployment config.

---

## Ordering

Mappers in `streams[].mappers` run in array order. When chaining (e.g. hash then rename), put them in the order you want them applied. Reordering changes the result — hashing after renaming targets the new field name, which is rarely what you want.

A safe pattern when both hashing and renaming a sensitive column:

```yaml
mappers:
  - type: hashing
    mapperConfiguration:
      { targetField: email, method: SHA-256, fieldNameSuffix: _hashed }
  - type: field-filtering
    mapperConfiguration: { targetField: email } # drop the plaintext column
```

This produces only `email_hashed` in BigQuery — the original `email` never lands.
