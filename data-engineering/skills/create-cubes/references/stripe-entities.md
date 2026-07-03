# Stripe Entities Reference

## Table naming

Airbyte syncs Stripe tables with a configurable prefix (default: `stripe_`).
Inspect the BigQuery dataset to confirm:

```sql
SELECT table_name FROM `<dataset>.INFORMATION_SCHEMA.TABLES`
WHERE table_name LIKE '%customers%' OR table_name LIKE '%invoices%'
ORDER BY table_name LIMIT 20;
```

Throughout this document `<prefix>` is a placeholder for that prefix.

---

## Primary entities

| Cube name               | BigQuery table          | PK   | Notes                            |
| ----------------------- | ----------------------- | ---- | -------------------------------- |
| `<prefix>customers`     | `<prefix>customers`     | `id` | `name` is display name           |
| `<prefix>subscriptions` | `<prefix>subscriptions` | `id` | FK `customer` (→ customers.id)   |
| `<prefix>invoices`      | `<prefix>invoices`      | `id` | FK `customer`, FK `subscription` |

---

## Relationship graph

```
customers ──< subscriptions ──< invoices
    └────────────────────────< invoices
```

- customer → subscriptions: `one_to_many` via `subscriptions.customer = customers.id`
- customer → invoices: `one_to_many` via `invoices.customer = customers.id`
- subscription → invoices: `one_to_many` via `invoices.subscription = subscriptions.id`
- subscription → latest_invoice: `many_to_one` via `subscriptions.latest_invoice = latest_invoice.id`

---

## Standard cube definitions

### customers

```yaml
name: <prefix>customers
sql_table: "`<dataset>.<prefix>customers`"
joins:
  <prefix>subscriptions:
    relationship: one_to_many
    sql: "${CUBE}.id = ${<prefix>subscriptions.customer}"
  <prefix>invoices:
    relationship: one_to_many
    sql: "${CUBE}.id = ${<prefix>invoices.customer}"
```

### subscriptions

```yaml
name: <prefix>subscriptions
sql_table: "`<dataset>.<prefix>subscriptions`"
joins:
  <prefix>customers:
    relationship: many_to_one
    sql: "${CUBE}.customer = ${<prefix>customers.id}"
  <prefix>invoices:
    relationship: one_to_many
    sql: "${CUBE}.id = ${<prefix>invoices.subscription}"
  <prefix>latest_invoice:
    relationship: many_to_one
    sql: "${CUBE}.latest_invoice = ${<prefix>latest_invoice.id}"
```

### invoices

```yaml
name: <prefix>invoices
sql_table: "`<dataset>.<prefix>invoices`"
joins:
  <prefix>customers:
    relationship: many_to_one
    sql: "${CUBE}.customer = ${<prefix>customers.id}"
  <prefix>subscriptions:
    relationship: many_to_one
    sql: "${CUBE}.subscription = ${<prefix>subscriptions.id}"
```

---

## Special cube: latest_invoice

`latest_invoice` is an alias for the `invoices` table (public: false) used
exclusively for the `subscriptions.latest_invoice` FK join. Needed because
Cube.js does not support two joins to the same table under the same cube name.

```yaml
name: <prefix>latest_invoice
sql_table: "`<dataset>.<prefix>invoices`"
public: false
joins:
  <prefix>subscriptions:
    relationship: one_to_many
    sql: "${CUBE}.id = ${<prefix>subscriptions.latest_invoice}"
```

---

## Common pitfalls

1. **`latest_invoice` must be a separate cube** — subscriptions needs both `invoices` (for all invoices) and `latest_invoice` (for the most recent one). Same physical table, different cube names.
2. **FK column names without suffix** — `subscriptions.customer` is the raw Stripe customer ID (not `customer_id`). Same for `invoices.subscription` and `invoices.customer`. Check actual column names in INFORMATION_SCHEMA.
3. **Stripe IDs are strings** — all IDs start with a prefix (`cus_`, `sub_`, `in_`, etc.). No casting needed.
4. **Timestamps** — Stripe tables from Airbyte use `_airbyte_extracted_at` as the sync timestamp. Use it for `refresh_key`.
