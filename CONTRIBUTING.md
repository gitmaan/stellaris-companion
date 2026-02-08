# Contributing to Stellaris Companion

## Development Setup

```bash
# Clone the repo
git clone https://github.com/gitmaan/stellaris-companion.git
cd stellaris-companion

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Build the Rust parser (required)
cd stellaris-parser
cargo build --release
cd ..

# Copy environment template and add your keys
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY
```

## Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_signals.py -v
```

## Code Style

- Format Python code with `ruff format`
- Use type hints for function signatures
- Follow existing patterns in the codebase

## Commit Messages

Use conventional commit format:
- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation only
- `refactor:` code change that neither fixes a bug nor adds a feature
- `test:` adding or updating tests
- `chore:` maintenance tasks

## Pull Request Process

1. Create a branch from `main`
2. Make your changes
3. Ensure tests pass and Rust parser builds
4. Submit a PR with a clear description
