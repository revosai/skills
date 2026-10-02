# Editing a cube

Syntax is in [definition.md](definition.md).

## The catch: `definition` is replaced whole

An update stores the `definition` you send *instead of* the stored one.
Nothing is merged. Send `{ "measures": { "total_amount": … } }` alone, and
the cube loses its table, its dimensions, and its joins. That breaks the
org's model. **Always send the complete definition**: the current one with
your change applied.

## Steps

1. **Read fresh**, right before writing:
   `api_read { "resource": "cubes", "id": "<cube id>" }`. If you only know
   the name, list with `filter: "name == \"crm_deals\""` to get the id. Keep
   the full `definition` you got. It is your undo.
2. **If you're removing, renaming, or retyping anything**, run the
   dependency check in SKILL.md (*Who depends on a cube*) for that member.
   Tell the user what uses it before going ahead.
3. **Apply only the requested change** to a copy of the current definition.
   Leave every other key exactly as it was, including `meta`,
   `refresh_key`, and joins you weren't asked about.
4. **Write the whole thing**:
   `api_write { "resource": "cubes", "id": "<cube id>", "data": { "definition": { …complete… } } }`.
   Don't send `name` unless you're renaming the cube (see below).
5. **Verify** as in SKILL.md:
   - Run `meta` on the cube.
   - Run a 3-row query over the members you added or changed.
   - If either fails, write the saved definition back, check that `meta`
     compiles, and then tell the user.
6. **Read the cube back** and check that the stored `definition` has your
   change and kept everything else.

## Typical changes

- **Add a dimension or measure.** Find the column the same way as for a new
  cube (create.md, step 3). A time column gets `type: "time"`. Measures
  should reference dimensions (`"${amount}"`).
- **Fix a column or type.** Change the `sql` or `type` in place and keep the
  member's name. Tables and segments refer to members by name. Their
  conditions were chosen for the old type, so mention when a type change
  may affect them.
- **Add a join.** Add the target to `joins` after checking that:
  - the target cube exists;
  - both sides have the dimensions the `sql` compares;
  - the relationship is chosen deliberately (definition.md, *Joins*).

  Then check fan-out in step 5 by comparing the joined count with the
  cube's own count.
- **Remove a member or join.** Safe only if nothing uses it. A table column
  on a removed dimension makes that table's view fail to compile, and with
  it the whole org's model. Check first, every time.
- **Rename for display.** Change `title` (cube or member), not the name.
  Titles are what people see, and nothing references them.

## Renaming a cube or a member's key

Avoid it. The name is how everything else finds the cube or member:

- other cubes' joins and `${…}` references;
- tables' streams and columns;
- segments' join paths and filters.

Some of those can't be repointed through these tools. If the user wants a
different label, change `title`. If they truly need the new name, list
everything that refers to the old one, and say what will break. Proceed
only with their explicit go-ahead. Update the other cubes' references
together with the rename, so the model compiles at the end.

To rename the cube itself, send both `name` and `definition.name`, set to
the new name.
