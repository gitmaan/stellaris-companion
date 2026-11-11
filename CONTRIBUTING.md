# Contributing to Stellaris Companion

## What We're Prioritizing Right Now

To keep the app stable at launch, we are currently accepting contributions that focus on:

- DLC coverage and correctness
- Windows/Linux reliability fixes
- Stability and polish for existing features (bugs, regressions, tests, docs)

Please avoid net-new feature work for now unless it is required to fix a critical bug or platform issue.
If you're unsure whether a change fits, open an issue first and we will help scope it.

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
4. Confirm the change aligns with current priorities (DLC/platform/stability)
5. Submit a PR with a clear description

## Issue Lifecycle

Reporters only see what happens on their issue, so each state change gets a
comment written for them, in their language.

1. **Investigating.** Use `Related to #N` in PRs that help but don't fully fix
   the report. If the reporter could attach a save or diagnostics, ask for it.
2. **Fixed on `main`.** Comment with what changed and that it ships in the next
   release. Use `Related to #N` in the PR, not `Fixes #N`: GitHub closes the
   issue at merge, before any user can get the fix.
3. **Shipped in a beta.** Add the `fixed-in-beta` label and comment with the
   release link and how to opt in (Config → More Settings → Update Track → Beta).
   Ask the reporter to confirm.
4. **Shipped in stable.** Close with the stable release link and an invitation to
   reopen. Release PRs may use `Fixes #N` for issues that ship in that release.

Before closing a user-reported misreading (the Advisor or Chronicle got campaign
facts wrong), add a synthetic case to
[`tests/report_regressions/`](tests/report_regressions/README.md). Fixes that
were never guarded have come back (#11 returned as #44).

Close duplicates with a link to the issue that tracks the problem. If a report
contains a separate request, open an issue for it and link it.

### Crediting reporters

People who report problems put real time into this project. Credit them in the
squash-merge commit message of the fix:

- `Co-authored-by:` when their own analysis shaped the fix, for example they
  traced the cause or found the faulty code.
- `Reported-by:` when their report led to the fix.
- `Helped-by:` when they supplied something the fix depended on, such as a save.

Use GitHub's no-reply address, `ID+login@users.noreply.github.com` (the ID is in
`gh api users/<login>`), so no private email ends up in history. Then thank them
by @mention in the notes of the release that ships the fix.
