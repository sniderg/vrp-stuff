# ROADEF 2016 IRP Tools

Local tooling for ROADEF/EURO 2016 inventory routing experiments.

## Setup

```bash
uv sync
```

Run tools with:

```bash
uv run roadef-tools --help
```

See [SOLVER_INTEGRATION.md](SOLVER_INTEGRATION.md) for the ALNS/MILP integration layout.

The official checker is a bundled Mono executable under `roadef_2016_data/checker_v2`.
Install Mono separately if you want `--official` checker runs.
