# Jira Entities Reference

## Table naming

Airbyte syncs Jira tables with a configurable prefix (default: `jira_`).
Inspect the BigQuery dataset to find the actual prefix:

```sql
SELECT table_name FROM `<dataset>.INFORMATION_SCHEMA.TABLES`
WHERE table_name LIKE '%issues%' OR table_name LIKE '%projects%'
ORDER BY table_name LIMIT 20;
```

Throughout this document `<prefix>` is a placeholder for that prefix.

---

## Primary entities

| Cube name                    | BigQuery table               | PK          | Notes                                            |
| ---------------------------- | ---------------------------- | ----------- | ------------------------------------------------ |
| `<prefix>issues`             | `<prefix>issues`             | `id`        | `key` is display name; metadata in `fields` JSON |
| `<prefix>projects`           | `<prefix>projects`           | `id`        | `name`                                           |
| `<prefix>issue_types`        | `<prefix>issue_types`        | `id`        | `name`                                           |
| `<prefix>issue_priorities`   | `<prefix>issue_priorities`   | `id`        | `name`                                           |
| `<prefix>users`              | `<prefix>users`              | `accountId` | `displayName`; aliased 4× (see below)            |
| `<prefix>sprints`            | `<prefix>sprints`            | `id`        | `name`; FK `boardId`                             |
| `<prefix>boards`             | `<prefix>boards`             | `id`        | `name`; FK `projectId`                           |
| `<prefix>issue_comments`     | `<prefix>issue_comments`     | —           | FK `issueId`; `author` is JSON object            |
| `<prefix>issue_worklogs`     | `<prefix>issue_worklogs`     | —           | FK `issueId`; `author` is JSON object            |
| `<prefix>project_components` | `<prefix>project_components` | —           | FK `projectId` as INT64                          |
| `<prefix>project_versions`   | `<prefix>project_versions`   | —           | FK `projectId` as INT64                          |

---

## Users table aliasing

The single `<prefix>users` table must be exposed as **separate cubes** for each
role because Cube.js does not support joining the same table twice with
different conditions. Each alias has its own cube name and `sql_table` pointing
to the same physical table.

| Cube name                      | Role           | Join condition on `<prefix>issues`                 |
| ------------------------------ | -------------- | -------------------------------------------------- |
| `<prefix>users_assignee`       | Assignee       | `JSON_VALUE(fields, '$.assignee.accountId')`       |
| `<prefix>users_reporter`       | Reporter       | `JSON_VALUE(fields, '$.reporter.accountId')`       |
| `<prefix>users_creator`        | Creator        | `JSON_VALUE(fields, '$.creator.accountId')`        |
| `<prefix>users_comment_author` | Comment author | `JSON_VALUE(issue_comments.author, '$.accountId')` |
| `<prefix>users_worklog_author` | Worklog author | `JSON_VALUE(issue_worklogs.author, '$.accountId')` |
| `<prefix>users`                | Direct queries | (no joins defined)                                 |

Template for each alias:

```yaml
name: <prefix>users_assignee
sql_table: "`<dataset>.<prefix>users`"
joins:
  <prefix>issues:
    relationship: one_to_many
    sql: >
      ${CUBE}.accountId =
      JSON_VALUE(${<prefix>issues.fields}, '$.assignee.accountId')
```

Corresponding join on `<prefix>issues`:

```yaml
joins:
  <prefix>users_assignee:
    relationship: many_to_one
    sql: >
      JSON_VALUE(${CUBE}.fields, '$.assignee.accountId') =
      ${<prefix>users_assignee.accountId}
```

---

## Issues: fields JSON column

Issue metadata lives in a single `fields` JSON column. Extract with `JSON_VALUE`:

| Field               | JSON path                                 |
| ------------------- | ----------------------------------------- |
| Issue type ID       | `$.issuetype.id`                          |
| Priority ID         | `$.priority.id`                           |
| Assignee account ID | `$.assignee.accountId`                    |
| Reporter account ID | `$.reporter.accountId`                    |
| Creator account ID  | `$.creator.accountId`                     |
| Status              | `$.status.name`                           |
| Summary             | `$.summary`                               |
| Story points        | `$.story_points` or `$.customfield_10016` |

Example dimension:

```yaml
dimensions:
  status:
    sql: "JSON_VALUE(${CUBE}.fields, '$.status.name')"
    type: string
  issue_type_name:
    sql: "JSON_VALUE(${CUBE}.fields, '$.issuetype.name')"
    type: string
```

---

## Bridge / junction cubes (public: false)

### sprint_issues

Sprints and issues are many-to-many. The `sprint_issues` table has columns
`issueId` (STRING) and `sprintId` (INT64). Composite PK required.

```yaml
name: <prefix>sprint_issues
sql_table: "`<dataset>.<prefix>sprint_issues`"
public: false
dimensions:
  id:
    sql: "${CUBE}.issueId || '_' || CAST(${CUBE}.sprintId AS STRING)"
    type: string
    primary_key: true
joins:
  <prefix>issues:
    relationship: many_to_one
    sql: "${CUBE}.issueId = ${<prefix>issues.id}"
  <prefix>sprints:
    relationship: many_to_one
    sql: "${CUBE}.sprintId = ${<prefix>sprints.id}"
```

Issues and sprints join through this bridge:

```yaml
# On <prefix>issues:
joins:
  <prefix>sprint_issues:
    relationship: one_to_many
    sql: "${CUBE}.id = ${<prefix>sprint_issues.issueId}"

# On <prefix>sprints:
joins:
  <prefix>sprint_issues:
    relationship: one_to_many
    sql: "${CUBE}.id = ${<prefix>sprint_issues.sprintId}"
```

### board_issues

Board issues (`board_issues` table) link boards to issues. Composite PK uses `id` + `boardId`.

```yaml
name: <prefix>board_issues
sql_table: "`<dataset>.<prefix>board_issues`"
public: false
dimensions:
  composite_id:
    sql: "${CUBE}.id || '_' || CAST(${CUBE}.boardId AS STRING)"
    type: string
    primary_key: true
joins:
  <prefix>issues:
    relationship: many_to_one
    sql: "${CUBE}.id = ${<prefix>issues.id}"
  <prefix>boards:
    relationship: many_to_one
    sql: "${CUBE}.boardId = ${<prefix>boards.id}"
```

---

## Type casting pitfalls

### project_components / project_versions → projects

`project_components.projectId` and `project_versions.projectId` are INT64 but
`projects.id` is STRING. Always cast:

```yaml
# On <prefix>project_components:
joins:
  <prefix>projects:
    relationship: many_to_one
    sql: "CAST(${CUBE}.projectId AS STRING) = ${<prefix>projects.id}"

# On <prefix>projects:
joins:
  <prefix>project_components:
    relationship: one_to_many
    sql: "SAFE_CAST(${CUBE}.id AS INT64) = ${<prefix>project_components.projectId}"
```

---

## Common pitfalls

1. **`fields` JSON column** — most issue attributes live here, not as top-level columns. Always check `INFORMATION_SCHEMA` before assuming a column exists at the top level.
2. **User aliases must be separate cubes** — do not try to join `users` twice from `issues`; Cube.js requires distinct cube names per join target.
3. **`sprintId` is INT64** — cast to STRING in the composite PK to avoid type errors.
4. **`issue_comments.author` is a JSON object** — extract `accountId` with `JSON_VALUE`, not a direct column reference.
5. **`boards.projectId` vs `projects.id`** — both are strings here; no cast needed. But `project_components.projectId` is INT64 — always cast.
