# Join Validation SQL Templates

All queries use the literal `<dataset>` value resolved at the start of Phase 2. Substitute the placeholder before executing.

## Table of Contents

- [1. Key Uniqueness](#1-key-uniqueness)
- [2. Many-to-One Direction](#2-many-to-one-direction)
- [3. Reverse One-to-Many Direction](#3-reverse-one-to-many-direction)
- [4. One-to-One Relationships](#4-one-to-one-relationships)
- [5. Many-to-Many Through Bridge](#5-many-to-many-through-bridge)
- [6. JSON / Array Relationships](#6-json--array-relationships)
- [7. Type Compatibility](#7-type-compatibility)

---

## 1. Key Uniqueness

```sql
SELECT
  COUNT(*) AS total_rows,
  COUNT(DISTINCT <candidate_pk>) AS distinct_keys,
  COUNT(*) - COUNT(DISTINCT <candidate_pk>) AS duplicate_count
FROM `<dataset>.<gold_model>`;
```

A primary key should have `duplicate_count = 0`. If duplicates exist, do not mark the column as `primary_key: true` unless clearly documented.

---

## 2. Many-to-One Direction

Example: `deals.company_id -> companies.id` (many_to_one).

Validate FK match rate:

```sql
SELECT
  COUNT(*) AS total_rows_with_fk,
  COUNT(c.id) AS matched_rows,
  COUNT(*) - COUNT(c.id) AS unmatched_rows,
  ROUND(100.0 * COUNT(c.id) / COUNT(*), 2) AS match_percentage
FROM `<dataset>.gold_hubspot_deals` d
LEFT JOIN `<dataset>.gold_hubspot_companies` c
  ON d.company_id = c.id
WHERE d.company_id IS NOT NULL;
```

Check for fan-out (should be empty for valid many-to-one):

```sql
SELECT
  d.deal_id,
  COUNT(c.id) AS matched_companies
FROM `<dataset>.gold_hubspot_deals` d
LEFT JOIN `<dataset>.gold_hubspot_companies` c
  ON d.company_id = c.id
WHERE d.company_id IS NOT NULL
GROUP BY d.deal_id
HAVING COUNT(c.id) > 1
LIMIT 20;
```

---

## 3. Reverse One-to-Many Direction

Validate reverse aggregation:

```sql
SELECT
  c.id AS company_id,
  COUNT(d.deal_id) AS deal_count
FROM `<dataset>.gold_hubspot_companies` c
LEFT JOIN `<dataset>.gold_hubspot_deals` d
  ON c.id = d.company_id
GROUP BY c.id
ORDER BY deal_count DESC
LIMIT 20;
```

Cross-check sampled counts:

```sql
SELECT
  company_id,
  COUNT(*) AS expected_deal_count
FROM `<dataset>.gold_hubspot_deals`
WHERE company_id IN (<sample_company_ids>)
GROUP BY company_id;
```

Counts must match.

---

## 4. One-to-One Relationships

Validate uniqueness on both sides, then validate the join:

```sql
SELECT
  COUNT(*) AS total_rows,
  COUNT(r.<right_key>) AS matched_rows,
  COUNT(*) - COUNT(r.<right_key>) AS unmatched_rows,
  ROUND(100.0 * COUNT(r.<right_key>) / COUNT(*), 2) AS match_percentage
FROM `<dataset>.<left_model>` l
LEFT JOIN `<dataset>.<right_model>` r
  ON l.<left_key> = r.<right_key>
WHERE l.<left_key> IS NOT NULL;
```

Also validate reverse. If either side has duplicate keys, the relationship is not one-to-one.

---

## 5. Many-to-Many Through Bridge

Validate both bridge edges. Example: `companies <-> deals through gold_companies_deals`.

Bridge to one parent:

```sql
SELECT
  COUNT(*) AS total_bridge_rows,
  COUNT(c.id) AS matched_companies,
  COUNT(*) - COUNT(c.id) AS unmatched_companies,
  ROUND(100.0 * COUNT(c.id) / COUNT(*), 2) AS match_percentage
FROM `<dataset>.gold_companies_deals` b
LEFT JOIN `<dataset>.gold_hubspot_companies` c
  ON b.company_id = c.id
WHERE b.company_id IS NOT NULL;
```

Run analogous query for the other parent. Then validate reverse aggregations:

```sql
SELECT
  c.id AS company_id,
  COUNT(b.deal_id) AS related_deals
FROM `<dataset>.gold_hubspot_companies` c
LEFT JOIN `<dataset>.gold_companies_deals` b
  ON c.id = b.company_id
GROUP BY c.id
ORDER BY related_deals DESC
LIMIT 20;
```

Same query swapped for deals -> bridge -> companies. Report sampled counts.

---

## 6. JSON / Array Relationships

Validate extracted keys:

```sql
WITH extracted AS (
  SELECT DISTINCT
    src.<source_pk> AS source_id,
    extracted_id
  FROM `<dataset>.<source_model>` src,
  UNNEST(JSON_VALUE_ARRAY(src.<json_array_column>)) AS extracted_id
)
SELECT
  COUNT(*) AS total_relationships,
  COUNT(tgt.<target_pk>) AS matched_relationships,
  COUNT(*) - COUNT(tgt.<target_pk>) AS unmatched_relationships,
  ROUND(100.0 * COUNT(tgt.<target_pk>) / COUNT(*), 2) AS match_percentage
FROM extracted e
LEFT JOIN `<dataset>.<target_model>` tgt
  ON e.extracted_id = tgt.<target_pk>;
```

Sample matched values:

```sql
WITH extracted AS (
  SELECT DISTINCT
    src.<source_pk> AS source_id,
    extracted_id
  FROM `<dataset>.<source_model>` src,
  UNNEST(JSON_VALUE_ARRAY(src.<json_array_column>)) AS extracted_id
)
SELECT
  e.source_id, e.extracted_id, tgt.<target_pk>, tgt.<display_column>
FROM extracted e
LEFT JOIN `<dataset>.<target_model>` tgt
  ON e.extracted_id = tgt.<target_pk>
LIMIT 10;
```

---

## 7. Type Compatibility

```sql
SELECT column_name, data_type
FROM `<dataset>.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name IN ('<source_model>', '<target_model>')
  AND column_name IN ('<foreign_key>', '<target_pk>');
```

If types differ:

1. Report the mismatch.
2. Prefer fixing type alignment in the dbt model or approved support model.
3. Only cast in Cube join SQL when necessary.
4. Prefer casting the foreign-key side to match the primary-key side.
