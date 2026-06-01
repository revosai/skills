# Edge Cases

## User asks for a model but does not provide the SQL

```text
I can scaffold the model file and schema entry, but I need to know what the
transformation should produce.

Could you tell me:
1. What source model(s) or tables does it read from?
2. What columns should it expose, and what is the primary key?
3. Any filtering, aggregation, or join logic?

Alternatively, if this is a bridge model from a JSON array, I can apply the
standard bridge template — just tell me the source model and the JSON column.
```

## User asks for a "quick" or "simple" model without details

Same response as above. Do not invent business logic.

## Model depends on another model that does not exist yet

```text
The transformation you described references `<missing_model>`, which does not
exist in dbt/models/. Should I create that model first?
```

## Source is a raw table not yet declared as a dbt source

Declare it under `sources: - name: bronze` in `dbt/models/bronze/schema.yml`
first (see [schema-conventions.md](schema-conventions.md)), then reference it
with `{{ source('bronze', '<table>') }}` in the silver model SQL. Do not use
fully qualified BigQuery names directly — that bypasses dbt's dependency
graph and source freshness tracking.

## User asks to create a bronze SQL model

Refuse and redirect:

```text
Bronze is not a SQL layer in this project — `dbt/models/bronze/` only
contains `schema.yml` declaring raw tables as sources. Silver reads raw
data directly via `{{ source('bronze', '<raw_table>') }}`.

Should I create this as a silver model instead?
```

Do not generate any file under `dbt/models/bronze/` other than `schema.yml`.

## run fails

1. Show the error verbatim — do not paraphrase warehouse errors.
2. Offer to fix the SQL based on the error message.
3. Do not proceed to `dbt test` until run succeeds.

## test fails

Show which test failed and explain the likely cause:

- `unique` on PK fails → real duplicates exist; PK detection was wrong or source has unexpected duplicates needing `DISTINCT` or `ROW_NUMBER` dedup.
- `not_null` on a column fails → source has nulls; either the column is genuinely nullable (remove the test) or filter them out in SQL.

Ask the user how to proceed.
