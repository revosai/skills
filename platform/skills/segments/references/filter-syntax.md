# Segment filter syntax

A segment's `filter` is RevOS's own condition tree. RevOS translates it into
Cube.js filters when it evaluates the segment, so the vocabulary below is
what you write — not Cube's `equals`/`gt`/`inDateRange`.

## Shape

```json
{
  "combinationMode": "AND",
  "items": [ <condition or group>, … ]
}
```

- **Root**: `combinationMode` (`"AND"` | `"OR"`, AND when omitted) and
  `items`. `{}` is a valid filter and matches every record of the root cube.
- **Group**: `{ "filterType": "Group", "combinationMode": "AND" | "OR", "items": [ … ] }`.
  All three keys are required. Groups can nest, but the RevOS UI only edits
  one level of nesting — stay at one level unless the logic truly needs more,
  so the user can still open the segment in the UI.
- **Condition**: `{ "member": "<cube>.<member>", "type": "<OPERATOR>", "value": <string | number> }`.
  Segments always address members by `member` (the `columnId` form is for
  table views, not segments).

## Operators by member type

Pick the operator from the member's `type` in the cube's `meta`:

| Member type | Operators |
|---|---|
| `string` | `EQUAL`, `NOT_EQUAL`, `CONTAIN`, `NOT_CONTAIN`, `EMPTY`, `NOT_EMPTY` |
| `number`, and **every measure** | `EQUAL`, `NOT_EQUAL`, `GREATER_THAN`, `GREATER_THAN_OR_EQUAL`, `LESS_THAN`, `LESS_THAN_OR_EQUAL`, `EMPTY`, `NOT_EMPTY` |
| `boolean` | `CHECKED`, `NOT_CHECKED` |
| `time` (date / datetime) | the six comparisons above, `EMPTY`, `NOT_EMPTY`, `IS`, `IS_NOT` |

What they become in Cube, for reasoning about results:

| RevOS | Cube |
|---|---|
| `EQUAL` / `NOT_EQUAL` | `equals` / `notEquals` |
| `GREATER_THAN` … `LESS_THAN_OR_EQUAL` | `gt` / `gte` / `lt` / `lte` |
| `CONTAIN` / `NOT_CONTAIN` | `contains` / `notContains` (substring) |
| `EMPTY` / `NOT_EMPTY` | `notSet` / `set` |
| `CHECKED` / `NOT_CHECKED` | equals `"true"` / equals `"false"` |
| `IS` `TODAY` | within today |
| `IS` `IN_THE_FUTURE` / `IN_THE_PAST` | after / before now |
| `IS_NOT` … | the inverse of the matching `IS` |

## Rules the JSON schema doesn't show

The server enforces these on save, so a body that passes `api_details` can
still be rejected:

- Every condition needs `member`.
- `value` is **required** for every operator except `EMPTY`, `NOT_EMPTY`,
  `CHECKED`, `NOT_CHECKED` — and should be omitted for those four.
- `IS` / `IS_NOT` take exactly one of `"TODAY"`, `"IN_THE_FUTURE"`,
  `"IN_THE_PAST"`. Relative ranges like "last 30 days" aren't expressible as
  `IS`; use a comparison against a concrete date instead, and tell the user
  the date is fixed rather than rolling.
- `value` is a single string or number. There is no "in" list — "stage is
  A, B, or C" is an OR group of three `EQUAL`s; "stage is none of A, B" is
  an AND group of `NOT_EQUAL`s.

And one the server *doesn't* enforce: a condition whose `member` doesn't
exist saves fine and makes evaluation fail later (`status: "FAILED"`). Copy
member names from `meta`.

## Values

- Strings match exactly and case-sensitively for `EQUAL` — check the real
  values before writing one with a cubes query on that dimension
  (`api_read { "resource": "cubes", "method": "query", "body": { "query": { "dimensions": ["<cube>.<dim>"], "limit": 20 } } }`):
  is it `"won"`, `"closedwon"`, or `"Closed Won"`?
- Numbers can be sent as numbers (`3`) or strings (`"3"`); prefer numbers.
- Dates the UI writes: `"yyyy-MM-dd"` for date members, a full ISO timestamp
  for datetime members.

## Examples

Any of several values (OR group inside the root AND):

```json
{ "combinationMode": "AND", "items": [
  { "filterType": "Group", "combinationMode": "OR", "items": [
    { "member": "crm_deals.stage", "type": "EQUAL", "value": "discovery" },
    { "member": "crm_deals.stage", "type": "EQUAL", "value": "proposal" } ] },
  { "member": "crm_deals.amount", "type": "GREATER_THAN", "value": 50000 } ] }
```

Presence and booleans (no `value`):

```json
{ "combinationMode": "AND", "items": [
  { "member": "crm_companies.domain", "type": "NOT_EMPTY" },
  { "member": "crm_companies.is_customer", "type": "CHECKED" } ] }
```

A measure on a child cube the root has many of — the fan-out-safe way to say
"has at least N":

```json
{ "combinationMode": "AND", "items": [
  { "member": "crm_deals.count", "type": "GREATER_THAN_OR_EQUAL", "value": 3 } ] }
```
