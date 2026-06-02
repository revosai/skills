# RevOS Skills

Public, version-controlled home of the [RevOS](https://revos.ai)
[Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview).

Skills are grouped into **bundles** — one top-level directory per bundle, each a
plugin in the [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)
catalog. Install a whole bundle by pointing your tool at its directory.

## Bundles

### `data-engineering`

End-to-end RevOS data-engineering workflow. Installed by default when you scaffold
a project with `revos init`.

| Skill | What it does |
|---|---|
| [`create-connections`](data-engineering/create-connections) | Author a RevOS Connection YAML to sync a Source into the warehouse. |
| [`load-sample-data`](data-engineering/load-sample-data) | Populate a BigQuery dataset with sample data via `bq cp`. |
| [`explore-lakehouse`](data-engineering/explore-lakehouse) | Inspect the BigQuery lakehouse — datasets, schemas, sample rows, null rates. |
| [`create-dbt-transformations`](data-engineering/create-dbt-transformations) | Build dbt silver/gold models and declare raw sources. |
| [`create-cubes`](data-engineering/create-cubes) | Generate Cube.dev cube definitions from dbt gold models. |
| [`query-semantic-model`](data-engineering/query-semantic-model) | Run a Cube.js query and render the result inline as a table / chart. |
| [`visualize-semantic-model`](data-engineering/visualize-semantic-model) | Render a `model-graph.png` of the cube relationships. |

## Install

### skills.sh (`npx skills`)

[skills.sh](https://skills.sh) (the open `npx skills` tool) installs straight from
this GitHub repo. Point it at a **bundle directory** to install that whole bundle:

```bash
# Install the data-engineering bundle into the current project (.claude/skills/)
npx skills add revosai/skills/data-engineering --copy

# List the skills in a bundle without installing
npx skills add revosai/skills/data-engineering --list

# Target a specific agent / install globally / non-interactive
npx skills add revosai/skills/data-engineering -a claude-code -g --copy -y
```

`--copy` writes real files (committable, no symlinks). `-a` targets an agent
(`claude-code`, `cursor`, `opencode`, …), `-g` installs into your user dir, `-y`
skips prompts. Refresh later with `npx skills update`.

### Claude Code (plugin marketplace)

Each bundle is also a plugin in the `revos` marketplace:

```bash
/plugin marketplace add revosai/skills
/plugin install data-engineering@revos
```

### Manual

Each skill is a self-contained folder under its bundle (e.g.
[`data-engineering/`](data-engineering)) with a `SKILL.md` (plus optional
`references/` and `scripts/`). Copy a skill folder into the directory your agent
watches — e.g. `.claude/skills/<name>/` (project) or `~/.claude/skills/<name>/`
(global).

## Structure

```
.
├── .claude-plugin/
│   └── marketplace.json       # Claude Code marketplace manifest (one plugin per bundle)
└── <bundle>/                  # e.g. data-engineering/
    └── <skill-name>/
        ├── SKILL.md           # YAML frontmatter (name, description) + instructions
        ├── references/        # optional, loaded on demand
        └── scripts/           # optional executables
```

To add a new bundle: create a top-level `<bundle>/` directory of skill folders and
add a matching plugin entry to `marketplace.json`.

## License

[MIT](LICENSE)
