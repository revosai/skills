# RevOS Skills

Public, version-controlled home of the [RevOS](https://revos.ai) data-engineering
[Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview).

## Skills

| Skill | What it does |
|---|---|
| [`create-connections`](skills/create-connections) | Author a RevOS Connection YAML to sync a Source into the warehouse. |
| [`load-sample-data`](skills/load-sample-data) | Populate a BigQuery dataset with sample data via `bq cp`. |
| [`explore-lakehouse`](skills/explore-lakehouse) | Inspect the BigQuery lakehouse — datasets, schemas, sample rows, null rates. |
| [`create-dbt-transformations`](skills/create-dbt-transformations) | Build dbt silver/gold models and declare raw sources. |
| [`create-cubes`](skills/create-cubes) | Generate Cube.dev cube definitions from dbt gold models. |
| [`query-semantic-model`](skills/query-semantic-model) | Run a Cube.js query and render the result inline as a table / chart. |
| [`visualize-semantic-model`](skills/visualize-semantic-model) | Render a `model-graph.png` of the cube relationships. |

## Install

### Claude Code (plugin marketplace)

```bash
/plugin marketplace add revosai/skills
/plugin install revos-data-engineering@revos-skills
```

### Any agent (skills.sh / SkillUse / manual)

Each skill is a self-contained folder under [`skills/`](skills) with a `SKILL.md`
(plus optional `references/` and `scripts/`). Point your skill registry at this
repo, or copy a skill folder into the directory your agent watches
(e.g. `.claude/skills/<name>/` or `~/.claude/skills/<name>/`).

## Structure

```
.
├── .claude-plugin/
│   └── marketplace.json     # Claude Code marketplace manifest
└── skills/
    └── <skill-name>/
        ├── SKILL.md         # YAML frontmatter (name, description) + instructions
        ├── references/      # optional, loaded on demand
        └── scripts/         # optional executables
```

## License

[MIT](LICENSE)
