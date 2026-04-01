# Proof

A lightweight evaluation and reliability harness for agentic LLM systems.

Proof benchmarks task success, latency, cost, retries, fallback behavior, and failure modes across prompts, models, and routing strategies.

## Why

Most LLM repos show demos. Proof shows whether they work.

It answers: what is the success rate, what does it cost, how fast is it, where does it fail, and did the last change make it better or worse.

## What it measures

| Metric | Description |
|--------|-------------|
| Success rate | Pass/fail per task, per config, per iteration |
| Latency | Wall-clock time per call, avg and p95 |
| Token usage | Input/output tokens per call |
| Cost | Estimated USD based on model pricing |
| Retries | How many retries before success/failure |
| Fallback path | Whether fallback model was used |
| Failure category | Classified using a structured taxonomy |

## Failure taxonomy

Proof classifies every result into one of these categories:

**Success states:** `success`, `retry_recovery`, `fallback_recovery`

**Partial failures:** `partial_completion`, `formatting_failure`, `schema_violation`

**Hard failures:** `wrong_file_modified`, `hallucinated_success`, `tool_failure`, `timeout`, `auth_error`, `rate_limit`, `context_overflow`, `unknown_error`

## Quick start

```bash
# Install
pip install -e ".[all]"

# List available benchmark tasks
proof list

# Run a benchmark
proof run examples/compare_models.yaml --stdout

# Run with simulated provider (no API key needed)
proof run examples/demo_simulated.yaml --stdout
```

## Project structure

```
proof/
├── proof/              # Core package
│   ├── cli.py          # CLI entry point
│   ├── config.py       # Run configuration
│   ├── runner.py       # Task execution engine
│   ├── scorer.py       # Rule-based scoring
│   ├── taxonomy.py     # Failure classification
│   ├── cost.py         # Token counting and cost estimation
│   ├── reporter.py     # Markdown/JSON report generation
│   └── dashboard.py    # HTML dashboard generation
├── tasks/              # Benchmark task definitions (YAML)
├── examples/           # Example run configs
├── tests/              # Test suite
├── reports/            # Generated reports (gitignored)
└── dashboards/         # Generated dashboards (gitignored)
```

## Writing tasks

Tasks are YAML files in `tasks/`:

```yaml
id: config_edit
name: Edit a configuration file
category: code_edit
difficulty: easy
tags: [yaml, config, edit]

prompt: |
  Edit this YAML config. Change host to "db.prod.internal"...

context:
  config.yaml: |
    database:
      host: localhost

expected:
  contains:
    - "host: db.prod.internal"

scoring:
  mode: contains  # or: exact, regex, json_schema, multi
```

## Run configurations

Define what to benchmark in a YAML config:

```yaml
name: claude_vs_gpt4o
description: Compare Claude Sonnet vs GPT-4o on coding tasks

configs:
  - name: claude-sonnet
    provider: anthropic
    model: claude-sonnet-4-20250514
    system_prompt: "You are a precise coding assistant."

  - name: gpt-4o
    provider: openai
    model: gpt-4o
    system_prompt: "You are a precise coding assistant."

iterations: 3
max_retries: 1
fallback_config: claude-sonnet
timeout_seconds: 60
```

## Scoring modes

| Mode | Description |
|------|-------------|
| `contains` | Output must contain all specified substrings |
| `exact` | Output must exactly match expected output |
| `regex` | Output must match a regex pattern |
| `json_schema` | Output must be valid JSON with required keys |
| `multi` | Combine multiple check types |

## Supported providers

| Provider | Config value | Required package |
|----------|-------------|-----------------|
| Anthropic | `anthropic` | `pip install anthropic` |
| OpenAI | `openai` | `pip install openai` |
| Simulated | `simulate` | None (built-in, for testing) |

Adding a provider: implement an async `_call_<name>` function in `proof/runner.py`.

## Reports

Every run produces:

- **Markdown** — summary tables, failure taxonomy, detailed results
- **JSON** — machine-readable, full data for downstream analysis
- **HTML dashboard** — interactive charts (success rates, latency, cost, taxonomy breakdown)

## Roadmap

- [ ] LLM-as-judge scorer
- [ ] Version-to-version diff reports
- [ ] CI integration (GitHub Actions)
- [ ] More providers (Google, local models)
- [ ] Parallel task execution
- [ ] Cost budget limits

## License

MIT
