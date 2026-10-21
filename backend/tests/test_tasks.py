"""열린 작업 목록 도구. 규칙 기반이라 전부 글자로 검사된다.

마지막 검사만 가짜 저장소가 아니라 **실제 추적 문서**를 본다 — 규약 형태가 아닌
태스크 줄은 도구에 안 잡히고, 안 잡히면 조용히 사라지기 때문이다.
"""

from __future__ import annotations

import pytest

from tools import docptr, tasks

ROADMAP = """
# ROADMAP

## M1. 첫 마일스톤

- [x] M1-T1  끝난 것
- [ ] M1-T2  할 것
- [~] M1-T3  고쳤고 머지 대기

## M2. 둘째

- [ ] M2-T1  나중 것
"""

ISSUES = """
# ISSUES

## 문서

- [ ] H-007  늦게 난 결함
- [ ] H-002  먼저 난 결함
  `→ pkg/m.py::top`
"""

SOURCE = '"""모듈."""\n\n\ndef top() -> None:\n    """함수."""\n'


@pytest.fixture
def repo(tmp_path, monkeypatch):
    plan = tmp_path / "documents" / "plan"
    plan.mkdir(parents=True)
    (tmp_path / "pkg").mkdir()
    (plan / "ROADMAP.md").write_text(ROADMAP.lstrip(), encoding="utf-8")
    (plan / "ISSUES.md").write_text(ISSUES.lstrip(), encoding="utf-8")
    (plan / "DONE.md").write_text("# DONE\n\n### M1-T3 · 고친 것\n", encoding="utf-8")
    (tmp_path / "pkg" / "m.py").write_text(SOURCE, encoding="utf-8")
    monkeypatch.setattr(docptr, "ROOT", tmp_path)
    monkeypatch.setattr(docptr, "DOCS", tmp_path / "documents")
    monkeypatch.setattr(tasks, "PLAN", plan)
    return tmp_path


def test_merge_waiting_comes_first(repo):
    """`[~]` 는 가장 싸게 닫히고 가장 쉽게 잊힌다. 맨 앞이어야 한다."""
    out = tasks.render(tasks.scan_tasks())
    assert out.index("M1-T3") < out.index("H-002") < out.index("M1-T2")
    assert "머지 대기" in out.splitlines()[0]


def test_finished_tasks_are_not_shown(repo):
    assert "M1-T1" not in tasks.render(tasks.scan_tasks())


def test_defects_come_before_things_not_built_yet(repo):
    """지금 동작이 잘못된 것(H)이 아직 안 만든 것(M-T)보다 앞선다."""
    out = tasks.render(tasks.scan_tasks())
    assert out.index("H-007") < out.index("M1-T2") < out.index("M2-T1")


def test_a_code_pointer_is_shown_with_its_task(repo):
    assert "→ pkg/m.py::top" in tasks.render(tasks.scan_tasks())


def test_merge_waiting_with_detail_says_what_to_do(repo):
    assert "머지됐는지 확인" in tasks.render(tasks.scan_tasks())


def test_a_prefix_narrows_the_list(repo):
    out = tasks.render(tasks.scan_tasks(), "M2")
    assert "M2-T1" in out and "H-002" not in out and "M1-T2" not in out


def test_a_task_line_in_the_wrong_shape_is_caught(repo):
    doc = repo / "documents" / "plan" / "ISSUES.md"
    doc.write_text(doc.read_text() + "- [ ] 태그가 없는 줄\n", encoding="utf-8")
    bad = tasks.malformed_task_lines()
    assert len(bad) == 1 and "태그가 없는 줄" in bad[0]


def test_every_task_line_in_the_real_plan_docs_is_parseable():
    """가짜가 아니라 이 저장소의 ROADMAP · ISSUES 를 본다."""
    assert not tasks.malformed_task_lines()
