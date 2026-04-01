# Contributing to Proof

Thanks for your interest in contributing. This project is early-stage so things move fast.

## Setup

```bash
git clone https://github.com/kai-linux/proof.git
cd proof
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,all]"
```

## Running tests

```bash
pytest
```

## Code style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
ruff check .
ruff format .
```

## Adding tasks

Tasks live in `tasks/` as YAML files. See existing tasks for the schema. Each task needs:

- `id` — unique identifier (matches filename)
- `name` — human-readable name
- `prompt` — the prompt sent to the model
- `expected` — what constitutes a correct response
- `scoring` — how to evaluate (contains, exact, regex, json_schema)

## Adding providers

Provider integrations live in `proof/runner.py`. Add a new `_call_<provider>` async function and register it in `call_model()`.

## Pull requests

- Keep PRs small and focused
- Include a task YAML if adding a new benchmark scenario
- Run `ruff check` and `pytest` before submitting
