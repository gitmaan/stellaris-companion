# Experiments

This directory contains stress tests, benchmarks, and comparison scripts that were used during development. These are **not** unit tests - the actual test suite is in `tests/`.

## Running Experiments

Run from the project root:

```bash
# Set up environment
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Run a specific experiment
python experiments/test_fresh_stress.py
```

Or use the dotenv-compatible approach (these scripts look for `.env` in the project root):

```bash
cd /path/to/stellaris-companion
python experiments/benchmark_option_b.py
```

## Files

- `benchmark_*.py` - Performance comparisons
- `test_*_extraction.py` - Extractor validation
- `test_*_stress.py` - Stress tests for LLM behavior
- `test_optimized_*.py` - Prompt optimization experiments
