---
name: load-sample-data
description: >
  Populate a BigQuery dataset with sample data from public datasets using bq cp.
  Use when asked to: load sample data, populate the lakehouse, add demo data, seed the dataset,
  get started with sample tables, or when the user needs data to explore.
---

# Load Sample Data

Copy sample tables from `bigquery-public-data` into the user's dataset using `bq cp`. All copied tables are prefixed with `sample_` so they can be easily identified and cleaned up later.

## Environment

Verify env vars before running any command. If either is empty, ask the user to set it.

```bash
echo "Project: $GOOGLE_CLOUD_PROJECT"
echo "Dataset: $REVOS_BQ_DATASET"
```

- `$GOOGLE_CLOUD_PROJECT` — BQ project ID
- `$REVOS_BQ_DATASET` — target dataset

## Step 1: Check Existing Tables

```bash
bq ls $REVOS_BQ_DATASET
```

If tables exist, list them. They will be relevant in Step 3 for collision handling.

## Step 2: Present Sample Dataset Catalog

```text
Available sample datasets:

1. thelook_ecommerce (default) — B2C e-commerce data
   Tables: sample_users, sample_orders, sample_order_items, sample_products, sample_events, sample_inventory_items, sample_distribution_centers
   Rows: ~100K users, ~300K orders
   Good for: customer analytics, purchase funnels, product performance

2. google_analytics_sample — Web analytics session data
   Tables: sample_ga_sessions (single table, one day snapshot)
   Rows: ~900K sessions
   Good for: web traffic analysis, user behavior, channel attribution

3. austin_bikeshare — Bikeshare trip and station data
   Tables: sample_bikeshare_trips, sample_bikeshare_stations
   Rows: ~1.3M trips
   Good for: geospatial analysis, demand forecasting, utilization metrics
```

## Step 3: Copy Tables

If any table names from the chosen sample dataset collide with existing tables (from Step 1), ask the user whether to **overwrite** or **skip** each collision before copying. Skip collisions the user chose not to overwrite.

### thelook_ecommerce

```bash
for table in users orders order_items products events inventory_items distribution_centers; do
  echo "Copying sample_$table..."
  bq cp -f bigquery-public-data:thelook_ecommerce.$table \
    $GOOGLE_CLOUD_PROJECT:$REVOS_BQ_DATASET.sample_$table
done
```

### google_analytics_sample

The `ga_sessions` table is date-sharded. Copy a representative day:

```bash
echo "Copying sample_ga_sessions..."
bq cp -f bigquery-public-data:google_analytics_sample.ga_sessions_20170801 \
  $GOOGLE_CLOUD_PROJECT:$REVOS_BQ_DATASET.sample_ga_sessions
```

### austin_bikeshare

```bash
for table in bikeshare_trips bikeshare_stations; do
  echo "Copying sample_$table..."
  bq cp -f bigquery-public-data:austin_bikeshare.$table \
    $GOOGLE_CLOUD_PROJECT:$REVOS_BQ_DATASET.sample_$table
done
```

## Step 4: Verify

```bash
for table in <copied_tables>; do
  echo -n "$table: "
  bq query --nouse_legacy_sql --format=csv \
    "SELECT COUNT(*) FROM \`$GOOGLE_CLOUD_PROJECT.$REVOS_BQ_DATASET.$table\`" 2>/dev/null | tail -1
done
```

## Final Response

```text
Sample data loaded into $REVOS_BQ_DATASET.

Source: bigquery-public-data:<dataset_name>
Tables copied:
- <table_1>: <row_count> rows
- <table_2>: <row_count> rows

Next steps:
- Run "explore lakehouse" to inspect the data
- Run "create dbt transformations" to build bronze/silver/gold models
- Run "create cube" to generate Cube.dev semantic models
```

## Rules

- Use `bq cp -f` (not `CREATE TABLE AS SELECT`) — faster, no query costs, preserves schema. The `-f` flag is required to avoid cross-region confirmation prompts that block non-interactive shells.
- Show progress for each table being copied.
- Report any failures clearly with the `bq` error message.
- Always prefix destination tables with `sample_` — this allows easy identification and cleanup of sample data.
