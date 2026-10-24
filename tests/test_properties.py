"""Property-based tests (Hypothesis). CI uses a fixed seed profile; see conftest/hypothesis settings."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from tidymind import validator  # noqa: E402
from tidymind.errors import ModelResponseError, PlanFormatError  # noqa: E402
from tidymind.model_client import parse_suggestions  # noqa: E402
from tidymind.models import Plan, PlanItem  # noqa: E402
from tidymind.planner import parse_plan  # noqa: E402

FAST = settings(
    max_examples=200,
    derandomize=True,  # fixed seed: failures reproduce locally
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
names = st.text(max_size=300)


@FAST
@given(source=names, target=names)
def test_accepted_target_names_stay_inside_the_category_folder(source: str, target: str) -> None:
    if validator.source_name_problem(source) or validator.target_name_problem(source, target):
        return
    root = Path("/safe/root")
    item = PlanItem(source, 1, 1, "Documents", target, "")
    destination = validator.derive_destination(root, item)
    assert destination.parent == root / "Documents"
    assert destination.name == target
    assert ".." not in destination.parts


@FAST
@given(target=names)
def test_separators_and_traversal_never_pass(target: str) -> None:
    if any(ch in target for ch in "/\\\x00") or target in (".", ".."):
        assert validator.target_name_problem("a.pdf", target) is not None


@FAST
@given(category=names)
def test_unknown_categories_never_reach_execution(category: str, tmp_path_factory: pytest.TempPathFactory) -> None:
    from tidymind.models import CATEGORY_DIRS

    root = tmp_path_factory.mktemp("r").resolve()
    (root / "a.pdf").write_bytes(b"x")
    info = (root / "a.pdf").stat()
    item = PlanItem("a.pdf", info.st_size, info.st_mtime_ns, category, "a.pdf", "")
    report = validator.validate_plan(Plan(1, str(root), (item,)))
    assert report.results[0].ok == (category in CATEGORY_DIRS)


@FAST
@given(text=st.text(max_size=400))
def test_plan_parser_only_raises_controlled_errors(text: str) -> None:
    with contextlib.suppress(PlanFormatError):
        parse_plan(text)



@FAST
@given(
    value=st.recursive(
        st.none() | st.booleans() | st.integers() | st.text(max_size=20),
        lambda c: st.lists(c, max_size=4) | st.dictionaries(st.text(max_size=8), c, max_size=4),
        max_leaves=12,
    )
)

def test_model_parser_only_raises_controlled_errors(value: object) -> None:
    for expected in (0, 1, 3):
        with contextlib.suppress(ModelResponseError):
            parse_suggestions(json.dumps(value), expected)

