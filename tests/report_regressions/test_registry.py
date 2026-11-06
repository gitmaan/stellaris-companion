"""Keep the user-report registry honest: every case exists, runs, and passes."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

from .registry import ISSUE_URL, NOT_COVERED, REPORTS

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ISSUE_TEST = re.compile(r"^test_issue_(\d+)_\w+$")


def _registered_node_ids() -> list[str]:
    return [case.node_id for report in REPORTS.values() for case in report.cases]


def _issue_tests_in_this_directory() -> dict[str, ast.FunctionDef]:
    found: dict[str, ast.FunctionDef] = {}
    for path in sorted(HERE.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and ISSUE_TEST.match(node.name):
                rel = path.relative_to(REPO_ROOT).as_posix()
                found[f"{rel}::{node.name}"] = node
    return found


def test_every_report_has_a_case_and_no_report_is_both_covered_and_excluded():
    assert REPORTS
    assert not set(REPORTS) & set(NOT_COVERED)
    for issue, report in REPORTS.items():
        assert report.cases, f"#{issue} has no regression case"
        assert report.fixed_by, f"#{issue} does not name its fix"
        ids = [case.node_id for case in report.cases]
        assert len(ids) == len(set(ids)), f"#{issue} registers a node ID twice"


def test_new_cases_are_registered_named_and_linked_to_their_issue():
    issue_tests = _issue_tests_in_this_directory()
    new_cases = {
        case.node_id: issue
        for issue, report in REPORTS.items()
        for case in report.cases
        if case.origin == "new"
    }
    assert set(issue_tests) == set(new_cases), "register every test_issue_* case here"
    for node_id, function in issue_tests.items():
        issue = int(ISSUE_TEST.match(function.name).group(1))
        assert new_cases[node_id] == issue, f"{node_id} is registered under the wrong issue"
        docstring = ast.get_docstring(function) or ""
        assert ISSUE_URL.format(issue) in docstring, f"{node_id} must link its issue"


def test_every_registered_case_runs_and_passes_without_optional_fixtures():
    """Run each registered node ID in a child pytest; skips count as failures.

    Real-save tests skip in CI when the optional fixture is absent. A registered
    case must never depend on one, otherwise it would stop guarding its report.
    """
    node_ids = _registered_node_ids()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "-rA", *node_ids],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output[-4000:]

    passed = [line[len("PASSED ") :] for line in output.splitlines() if line.startswith("PASSED ")]
    for node_id in node_ids:
        matches = [p for p in passed if p == node_id or p.startswith(f"{node_id}[")]
        assert matches, f"registered case did not run and pass: {node_id}\n{output[-2000:]}"
    assert not re.search(r"\b\d+ (skipped|xfailed|xpassed)\b", output), output[-2000:]
