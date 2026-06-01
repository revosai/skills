---
name: visualize-semantic-model
description: >
  Generate a model-graph.png visualization of Cube.dev semantic models — render the
  cube graph, show relationships between cubes, draw the fact spine, or diagram the
  semantic layer. Use whenever the user mentions visualizing, drawing, diagramming, or
  graphing the semantic model / cube model / cube relationships, even if they don't
  explicitly ask for a PNG. Triggers: "visualize the semantic model", "draw the cube
  graph", "show relationships between cubes", "generate model-graph.png", "diagram the
  semantic layer", "render the cube model". Accepts an optional folder argument
  (defaults to `cubes/`).
---

# Visualize Semantic Model

Render a dark-themed directed graph of a Cube.dev model by parsing cube YAML files,
detecting the fact spine, then invoking the bundled renderer with a JSON spec.

The renderer (`scripts/render_graph.py`) is pure layout + drawing — it takes a graph
spec on stdin and writes the PNG. Keeping it bundled means every run produces visually
consistent output and you don't reinvent matplotlib code each time.

---

## Step 1: Resolve the cubes folder

If the user passed a folder argument, use it. Otherwise default to `cubes/`. If the
folder doesn't exist, ask the user where the cube definitions live before proceeding.

```bash
find <folder> -name "*.yml" -not -name "model-graph.*" | sort
```

---

## Step 2: Parse the cube graph

For each `.yml` file extract:

- `metadata.name` — cube name (the single source of truth for the cube identifier)
- `spec.meta.icon` — icon key if present (catalog key, `url:…`, or `data:…`); `null` if absent
- `spec.joins` — map of `target_cube → { relationship, sql }`
- A short join-key label parsed from each join's `sql`

**Join-key label rules.** Strip `${CUBE}.` and `${<target>}.` prefixes. For a single
equality, use the LHS column. For composite keys (multiple `AND`), join the LHS column
names with `+`.

```yaml
sql: "${CUBE}.user_id = ${users}.user_id"
# → "user_id"

sql: "${CUBE}.traffic_source = ${rev}.traffic_source AND ${CUBE}.order_date = ${rev}.order_date"
# → "traffic_source + order_date"
```

**Cardinality** (always render edges from the _one_ side to the _many_ side):

| Declared on this cube | This cube's side | Other cube's side |
| --------------------- | ---------------- | ----------------- |
| `many_to_one`         | ∞                | 1                 |
| `one_to_many`         | 1                | ∞                 |
| `one_to_one`          | 1                | 1                 |

**Fact-spine detection.** The cube with the most `many_to_one` joins (it holds the FKs)
is the spine. Tie-break by preferring names containing `enriched`, `fact`, or `items`.
If no cube has any `many_to_one` joins (e.g. the model is all `one_to_many` from a hub),
fall back to the cube with the most outgoing joins of any kind. If still ambiguous, ask
the user which cube to treat as the spine.

**Edge cases — stop and tell the user instead of rendering:**

- The folder contains fewer than 2 cubes → at least two cubes are needed.
- No `joins` found anywhere → there are no relationships to draw.

---

## Step 3: Build the graph spec

Build a JSON object the renderer understands:

```json
{
  "title": "Semantic Model — <project_name>",
  "fact_spine": {
    "name": "<fact_cube>",
    "icon": "<catalog_key_or_null>",
    "pk": "<pk_col>",
    "fks": ["fk_a", "fk_b", "fk_c", "fk_d"]
  },
  "dimensions": [
    {
      "name": "<dim_cube>",
      "icon": "<catalog_key_or_null>",
      "pk": "<pk_col>",
      "extras": ["metric1", "metric2"]
    }
  ],
  "edges": [
    {
      "from": "<dim_cube>",
      "to": "<fact_cube>",
      "label": "<join_key>",
      "from_card": "1",
      "to_card": "∞"
    }
  ]
}
```

`from_card` / `to_card` are the labels rendered at each end of the arrow — `"1"` or
`"∞"`. For `one_to_one` joins both ends are `"1"`.

The `icon` field is captured in the spec for future renderer support — the current
`render_graph.py` does not draw icons yet. Include it so the data is available when
the renderer is upgraded.

The arrow always points _from_ dimension _to_ fact, regardless of how the relationship
was declared on the YAML.

---

## Step 4: Render

```bash
python3 -c "import matplotlib" 2>/dev/null || python3 -m pip install matplotlib --quiet

python3 .claude/skills/visualize-semantic-model/scripts/render_graph.py \
  --output <folder>/model-graph.png \
  <<'EOF'
{ ... the JSON spec from Step 3 ... }
EOF
```

If `<folder>/model-graph.png` already exists and the user did not explicitly ask to
regenerate, ask before overwriting.

---

## Step 5: Show the result

Use the Read tool (not a Python `Read()` call — Read is a Claude Code tool) on the PNG
path so the image renders inline in chat:

> Read `<folder>/model-graph.png`

---

## Final response template

```text
Generated: <folder>/model-graph.png

Cubes visualized: <n>
Fact spine:       <cube_name>
Dimensions:       <dim1>, <dim2>, ...
Edges:            <dim1> → <fact>  (<join_key>)  [1:∞]
                  <dim2> → <fact>  (<join_key>)  [1:∞]
```

---

## Rules

- Always parse YAML — never hardcode cube names or relationships.
- Edge direction is always **dimension → fact** (arrow tail at dimension, head at fact).
- The `1` and `∞` markers are positioned by the renderer based on `from_card`/`to_card`;
  set them correctly per the cardinality table above.
- Do not overwrite an existing `model-graph.png` without confirming.
- After saving, always show the image inline using the Read tool.
