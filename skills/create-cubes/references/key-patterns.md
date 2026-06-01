# Key Detection Patterns

## Table of Contents

- [Primary Key Patterns](#primary-key-patterns)
- [Secondary Key Patterns](#secondary-key-patterns)
- [Foreign Key Patterns](#foreign-key-patterns)
- [JSON / Array Key Patterns](#json--array-key-patterns)
- [Schema Summary Output](#schema-summary-output)

---

## Primary Key Patterns

Common primary key column names:

```text
id
<entity>_id
<model_name>_id
uuid
unique_id
external_id
source_id
```

Examples:

```text
companies.id
companies.company_id
companies.office_unique_id
hubspot_companies.properties_company_unique_id
```

Rules:

1. Prefer a known business or platform identifier over a generated row number.
2. Prefer stable IDs over names or labels.
3. Do not mark a column as primary key only because it looks unique by name.
4. Validate uniqueness with SQL (see references/validation-queries.md, section 1).

---

## Secondary Key Patterns

Secondary keys are identifiers that are not the table primary key but can be used for joins, grouping, lookup, or `count_distinct` measures.

Common patterns:

```text
office_unique_id
company_id
customer_id
client_id
deal_id
contact_id
owner_id
user_id
account_id
product_id
address_id
external_id
source_id
```

Rules:

1. Track secondary keys explicitly.
2. Secondary keys may be foreign keys to another entity.
3. Secondary keys should usually become Cube dimensions.
4. Secondary keys may support `count_distinct` measures if analytically useful, but only inside the cube that owns the FK (see Phase 7 caution about fan-out).

---

## Foreign Key Patterns

Common patterns:

```text
<entity>_id
<entity>Id
fk_<entity>
associated_<entity>_id
parent_<entity>_id
owner_id
created_by_user_id
updated_by_user_id
```

Also check JSON and array-based foreign keys:

```text
deals.companies -> companies.id
companies.deals -> deals.id
contacts.associated_company_ids -> companies.id
```

---

## JSON / Array Key Patterns

Keys may be hidden inside JSON strings, JSON arrays, repeated fields, or nested structures. This is especially common for one-to-many and many-to-many relationships.

Common column names that may contain relationship keys:

```text
companies, deals, contacts, users, owners, clients, products, addresses
associations, associated_companies, associated_deals, associated_contacts
associated_clients, associated_products
company_ids, deal_ids, contact_ids, client_ids, product_ids, address_ids
```

Example: `gold_hubspot_deals.companies` may contain an array of company IDs.

For JSON arrays, use `UNNEST(JSON_VALUE_ARRAY(...))`.

Rules:

1. Always inspect JSON, array, repeated, and nested fields for hidden relationship keys.
2. Do not assume relationship keys only exist as flat columns.
3. If JSON structure is unknown, inspect sample values first:

```sql
SELECT <json_or_array_column>
FROM `<dataset>.<gold_model>`
WHERE <json_or_array_column> IS NOT NULL
LIMIT 20;
```

4. If a relationship is stored as an array of IDs, use or create an approved bridge/support model. Bridge model creation is delegated to `create-dbt-transformations`.
5. Bridge models should preserve both sides of the relationship as keys.
6. Bridge and junction cubes should use `public: false` where the project convention supports it.

---

## Schema Summary Output

After analysis, summarize each selected model in this format:

```text
Model: gold_hubspot_deals
Columns: 18
Candidate primary key: deal_id
Secondary keys: company_id, owner_id
JSON / array relationship columns: companies, contacts
Time columns: created_at, updated_at, closed_at
Numeric metric-like columns: amount
Airbyte columns present: _airbyte_extracted_at (will be exposed), _airbyte_raw_id, _airbyte_meta, _airbyte_generation_id (will be excluded by default)
```
