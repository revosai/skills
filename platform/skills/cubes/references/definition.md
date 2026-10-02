# Cube definition syntax

A stored `definition` is a Cube.js cube written in Cube's YAML-style keys:
snake_case, with `sql_table`, `primary_key`, and `refresh_key`. Write it the
way the org's existing cubes are written. Get one by id and copy its
conventions (dataset, quoting, `refresh_key`) before inventing your own.

```json
{
  "name": "crm_deals",
  "title": "Deals",
  "description": "One row per CRM deal.",
  "sql_table": "analytics.crm_deals",
  "data_source": "default",
  "refresh_key": { "sql": "SELECT MAX(_airbyte_extracted_at) FROM analytics.crm_deals" },
  "meta": { "abConnectionId": "<connection id>", "abStreamName": "deals" },
  "dimensions": {
    "id":         { "sql": "${CUBE}.`id`", "type": "string", "primary_key": true, "public": true },
    "stage":      { "sql": "${CUBE}.`stage`", "type": "string", "title": "Stage" },
    "amount":     { "sql": "${CUBE}.`amount`", "type": "number", "format": "currency" },
    "close_date": { "sql": "${CUBE}.`closeDate`", "type": "time" },
    "company_id": { "sql": "${CUBE}.`companyId`", "type": "string" }
  },
  "measures": {
    "count":        { "type": "count" },
    "total_amount": { "sql": "${amount}", "type": "sum", "format": "currency" },
    "won_count":    { "type": "count", "filters": [{ "sql": "${stage} = 'won'" }] }
  },
  "joins": {
    "crm_companies": { "relationship": "many_to_one", "sql": "${CUBE.company_id} = ${crm_companies.id}" }
  }
}
```

## Top level

- **`name`**: the identifier everything else uses: members (`crm_deals.stage`),
  joins, table streams, and segment join paths. Use letters, digits, and
  underscores. It must equal the record's top-level `name`. Never use the
  generated prefixes `model_` or `segment_`.
- **`sql_table`**: `<dataset>.<table>`. A connection's stream lands as
  `<connection prefix><stream name>`, so a HubSpot connection with prefix
  `hubspot_` puts the `deals` stream in `<dataset>.hubspot_deals`. Read the
  dataset from an existing cube's `sql_table`. Read the prefix and streams
  from `api_read { "resource": "connections" }`. Use `sql` with a `SELECT`
  instead only when the cube really needs a derived query.
- **`data_source`**: `"default"`.
- **`refresh_key`**: tells Cube when the data changed. For Airbyte-landed
  tables, use `MAX(_airbyte_extracted_at)` over the table, as the existing
  cubes do.
- **`meta`**: `abConnectionId` and `abStreamName` mark the connection and
  stream a cube reads. The RevOS UI uses them for the source icon and for
  table enrichment, so set them when the cube reads a connection's stream.
- **`title`** and **`description`**: what a person sees in RevOS and what
  query-semantic-model reads to pick a cube. Always write a one-line
  description.

## Dimensions

`type` is one of `string`, `number`, `boolean`, `time`, or `geo`. Dates and
timestamps must be `time`, or they can't be bucketed or used with date
filters.

- `sql` references a column of this cube's table as ``${CUBE}.`column` ``.
  The backticks are BigQuery quoting. If the org's existing cubes quote
  differently, follow them. Column names are case-sensitive, and the
  dimension's own name can differ from the column (`close_date` →
  `` `closeDate` ``).
- Give **exactly one** dimension `primary_key: true`. Primary keys are
  hidden by default, so add `public: true`. Joins, segments
  (`primaryKeyDimension`), tables, and Cube's de-duplication of joined
  measures all rely on it.
- Optional: `title`, `description`, and `format` (`currency`, `percent`,
  `id`, `link`, `imageUrl`). `case` derives labelled buckets:
  `{ "when": [{ "sql": "${CUBE}.amount > 50000", "label": "Large" }], "else": { "label": "Small" } }`.

## Measures

`type` is one of `count`, `count_distinct`, `count_distinct_approx`, `sum`,
`avg`, `min`, `max`, or `number` (a calculated measure).

- `count` needs no `sql`. **Give every cube a `count`**: segments express
  "has at least N of these" through the child cube's count, and query
  questions start there too.
- `sum`, `avg`, `min`, `max`, and `count_distinct` need `sql`. Prefer
  referencing a dimension (`"${amount}"`) over repeating the column.
- `number` combines other measures:
  `{ "sql": "${total_amount} / NULLIF(${count}, 0)", "type": "number" }`.
- `filters` restricts what a measure counts:
  `[{ "sql": "${stage} = 'won'" }]`. This is how you give segments a
  "count of won deals" to filter on without fanning out.

## Joins

Keys are the **target cube's name**. Each join has `relationship` and `sql`:

| relationship | meaning, from this cube | example |
|---|---|---|
| `many_to_one` | many of this per one target | deals → company |
| `one_to_many` | one of this per many targets | company → deals |
| `one_to_one` | at most one each way | organization → its subscription |

- `sql` compares dimensions on both sides:
  `${CUBE.company_id} = ${crm_companies.id}`. Both members must exist as
  dimensions, and the target cube must exist. A join to a missing cube or
  member breaks compilation for the whole org.
- Getting the relationship wrong doesn't error. It inflates or deflates
  measures across the join. Decide it from the data: which side holds the
  foreign key, and whether that key is unique. If unsure, check with a query
  (count of rows versus count of distinct key) or ask the user.
- Declare a join once, on the side where it reads most naturally. Usually
  that is the cube holding the foreign key (`many_to_one`). Cube can walk it
  from either end. Declaring both directions is allowed but adds a second
  path to keep consistent.

## References inside SQL

| You write | It means |
|---|---|
| `${CUBE}` | this cube's table (alias) |
| `${CUBE.member}` or `${member}` | a member of this cube |
| `${other_cube.member}` | a member of another cube, which must be joined |

Every `${…}` must resolve when the org's model compiles. A typo here is one
of the ways to break the whole model, so check names against the stored
definitions before writing.
