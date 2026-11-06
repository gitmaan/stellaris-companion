## Description
[What does this PR do?]

## Related issue
Related to #[issue number] (if applicable). Use `Fixes #N` only in a release PR that ships the fix; see the issue lifecycle in CONTRIBUTING.md.

- [ ] User-reported misreading: a synthetic case was added to `tests/report_regressions/`

## Priority alignment
- [ ] This PR aligns with current priorities: DLC coverage/correctness, Windows/Linux reliability, or stability of existing features
- [ ] If this is a new feature, I explained why it is critical right now

## DLC impact
- [ ] No DLC behavior changed
- [ ] DLC behavior changed; affected DLC(s) are listed in the PR description

## Platform validation
- [ ] I tested on Windows and/or Linux, or explained why that was not possible

## Regression risk
[Briefly describe possible regressions and how they were validated]

## Type of change
- [ ] Bug fix
- [ ] New feature
- [ ] Refactoring (no functional changes)
- [ ] Documentation

## Checklist
- [ ] Tests pass locally (`pytest tests/`)
- [ ] Rust parser builds (`cd stellaris-parser && cargo build --release`)
- [ ] No new warnings
- [ ] I have tested with a real Stellaris save file
