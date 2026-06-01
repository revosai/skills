---
name: explore-lakehouse
description: >
  Inspect the RevOS BigQuery lakehouse: list datasets and tables, introspect table schemas
  and column types, preview sample rows, assess data layers (bronze/silver/gold), and check
  data completeness and null rates. Required companion skill for create-dbt-transformations
  and create-cubes — load before generating dbt models or cube definitions to
  introspect warehouse columns and types. Use when asked to: explore the lakehouse, list
  BigQuery tables, inspect a table schema, preview data, check raw source tables, assess data
  quality, check null rates, understand available data, or perform BigQuery schema introspection.
---

# Explore Lakehouse

Use `bq` CLI to explore the BigQuery lakehouse for this project.

## Environment

Resolve connection details from env vars before running any command:

```bash
echo "Project: $GOOGLE_CLOUD_PROJECT"
echo "Dataset: $REVOS_BQ_DATASET"
```

- `$GOOGLE_CLOUD_PROJECT` — BQ project ID
- `$REVOS_BQ_DATASET` — default dataset (may be overridden by user)
- `INFORMATION_SCHEMA` queries: omit `--location` flag — use plain `bq query --nouse_legacy_sql`

## Commands

List tables in the org's dataset:

```bash
bq ls $REVOS_BQ_DATASET
```

List all datasets in the project (only if the user explicitly asks):

```bash
bq ls --project_id=$GOOGLE_CLOUD_PROJECT
```

Inspect a table schema (filter out internal columns):

```bash
bq show --schema --format=prettyjson $REVOS_BQ_DATASET.<table> | python3 -c "
import json, sys
cols = json.load(sys.stdin)
names = [c['name'] for c in cols if not c['name'].startswith('_airbyte')]
print('\n'.join(names))
"
```

Preview sample rows:

```bash
bq head -n 5 $REVOS_BQ_DATASET.<table>
```

Get row counts for a list of tables:

```bash
for table in table1 table2 table3; do
  echo -n "$table: "
  bq query --nouse_legacy_sql --format=csv \
    "SELECT COUNT(*) FROM \`$GOOGLE_CLOUD_PROJECT.$REVOS_BQ_DATASET.$table\`" 2>/dev/null | tail -1
done
```

Check null rates on a set of columns:

```bash
bq query --nouse_legacy_sql "
SELECT
  COUNTIF(col1 IS NULL) AS col1_null,
  COUNTIF(col2 IS NULL) AS col2_null,
  COUNT(*) AS total
FROM \`$GOOGLE_CLOUD_PROJECT.$REVOS_BQ_DATASET.<table>\`
"
```

## Workflows

### "What's in my database?" / general overview

1. List tables in the org's dataset: `bq ls $REVOS_BQ_DATASET`
2. If the dataset is empty (no tables), tell the user:
   - They can add data sources by running `revos sources create` to open the RevOS UI
   - They can view existing sources with `revos sources list`
   - Stop here — no further exploration is possible without data
3. Infer the data source and domain from table name prefixes (e.g. `salesforce_*`, `stripe_*`, `hubspot_*`)
4. Group tables by source/domain
5. Return: sources found, table count per source, table types (TABLE/VIEW), one-line description per group

### "What layer is this data?" / bronze–silver–gold assessment

1. Check dbt model folders: `find dbt/models -type f | sort`
2. If folders contain only `.gitkeep` → that layer hasn't been built yet
3. Assess the tables themselves:
   - **Bronze indicators:** raw source-prefixed names, many flat columns with source-system naming (e.g. `properties_*`, `fields_*`), no aggregations, no joins visible in schema
   - **Silver indicators:** cleaned column names, deduplicated, conformed types, `_id` foreign keys
   - **Gold indicators:** aggregated metrics, wide fact tables, business-named columns (`arr`, `churn_rate`, `ltv`)
4. Report which layers exist and which are missing

### "Is data complete?" / data quality check

1. Get all tables: `bq ls <dataset>`
2. For each table, fetch its schema to discover actual column names
3. Identify the business-critical columns from the schema — look for:
   - **Identity/key columns:** anything named `id`, `*_id`, `email`, `name`
   - **Date columns:** `created_at`, `*_date`, `*_at`
   - **Relationship columns:** foreign keys linking to other objects
   - **Core metric columns:** amounts, statuses, stages, owner assignments
4. Run a single `COUNTIF(col IS NULL)` query per table covering those columns
5. Where a source uses an `archived` / `is_deleted` flag, filter it out: `WHERE archived = false OR archived IS NULL`
6. Present results per table:

| Field | Nulls | % Missing | Status       |
| ----- | ----- | --------- | ------------ |
| ...   | ...   | ...%      | ✅ / ⚠️ / ❌ |

Status thresholds: ✅ < 5% · ⚠️ 5–50% · ❌ > 50%

7. Summarise findings: which tables are well-populated, which have critical gaps, and what that means for downstream use

### "What's in a specific table?"

1. `bq show --schema` — get full column list (omit `_airbyte_*` columns)
2. `SELECT COUNT(*)` — row count
3. `bq head -n 5` — sample rows
4. Identify and highlight the most important business columns from the schema

## Output rules

- Never mention Airbyte — it is an internal ETL mechanism invisible to users
- Do not reference `_airbyte_*` columns by name or explain their origin; omit them from schema summaries
- Describe data freshness neutrally: "updated daily" not "partitioned on `_airbyte_extracted_at`"
- Do not use phrases like "via Airbyte", "Airbyte's flat-column pattern", or "Airbyte artifact"
- Always discover table structure dynamically from the schema — never assume column names from a previous session
- Group output by integration source when listing many tables
- Note small row counts (< 100 rows) as a possible indicator of sandbox or test data
