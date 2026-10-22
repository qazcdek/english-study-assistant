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


# --- `[~]` 가 정말 머지됐는지 ---------------------------------------------------
#
# 실제 저장소 상태를 단정하는 검사는 두지 않는다 — 머지하면 깨지기 때문이다.
# 판단은 순수 함수에 몰아 두고 가짜 이력으로 본다. 저장소를 읽는 쪽은 읽히는지만 본다.

HISTORY = [
    ("a" * 40, "예문이 없다고 화면이 말하게 한다\n\nH-019"),
    ("b" * 40, "예문을 스키마 필수로 건다\n\nH-021"),
    ("c" * 40, "Merge pull request #18 from qazcdek/h019"),
    ("d" * 40, "주소를 고친다\n\nH-02"),
]


def test_a_tag_does_not_match_a_longer_one():
    """`H-02` 로 커밋을 찾을 때 `H-021` 이 끌려오면 머지 판정이 뒤집힌다."""
    assert tasks.tag_commits("H-02", HISTORY) == ["d" * 40]
    assert tasks.tag_commits("H-021", HISTORY) == ["b" * 40]


def test_a_merge_that_left_the_tip_behind_is_reported():
    """H-022 의 모양 그대로다 — 머지 커밋은 들어갔는데 브랜치 끝이 빠졌다."""
    shipped = {"a" * 40, "c" * 40}
    report = tasks.merge_report("H-021", HISTORY, "origin/main", shipped)
    assert "끝을 안 담았다" in report and "bbbbbbbbb" in report


def test_everything_shipped_says_to_check_it_off():
    report = tasks.merge_report("H-019", HISTORY, "origin/main", {"a" * 40})
    assert "전부 들어갔다" in report and "[x]" in report


def test_a_tag_with_no_commit_is_not_silent():
    """태그만 달고 커밋을 안 올린 경우. 조용히 '머지됨' 으로 보이면 안 된다."""
    report = tasks.merge_report("H-999", HISTORY, "origin/main", set())
    assert "못 찾았다" in report


def test_the_report_is_shown_on_the_waiting_line(repo):
    out = tasks.render(tasks.scan_tasks(), reports={"M1-T3": "origin/main 에 커밋 1/1개가 없다"})
    assert "origin/main 에 커밋 1/1개가 없다" in out
    assert "머지됐는지 확인" not in out  # 사람에게 묻는 옛 문구를 대체한다


def test_this_repository_can_actually_be_read():
    """순수 함수가 맞아도 git 을 못 읽으면 장치는 조용히 꺼진다.

    **커밋 개수나 기준 ref 의 존재를 단정하지 않는다.** CI 는 얕은 클론이라
    커밋 하나만 있고 `origin/main` 이 없다. 그걸 단정했다가 CI 가 깨졌다 (H-022).
    """
    history = tasks.commit_log()
    assert history is not None
    assert len(history) >= 1
    assert all(len(sha) == 40 and message for sha, message in history)


def test_a_missing_base_ref_says_so_instead_of_going_quiet(monkeypatch):
    """잴 수 없으면 **잴 수 없다고 말한다.** 조용히 빈 칸을 주면 옛 부탁으로 떨어진다."""
    monkeypatch.setattr(tasks, "base_ref", lambda: None)
    reports = tasks.merge_reports(["H-021"])

    assert reports["H-021"] == tasks.NO_BASE
    assert "재지 못했다" in reports["H-021"]


def test_the_waiting_line_never_falls_back_when_the_base_is_missing(repo, monkeypatch):
    """기준이 없을 때도 화면에는 사람에게 묻는 옛 문구가 아니라 이유가 뜬다.

    git 은 읽히는데 기준만 없는 상황이다. 그래서 `commit_log` 는 살려 둔다 —
    `repo` 픽스처의 tmp 디렉터리는 저장소가 아니라서 그냥 두면 git 이 아예 없는
    경우가 되고, 그건 다른 이야기다.
    """
    monkeypatch.setattr(tasks, "commit_log", lambda: HISTORY)
    monkeypatch.setattr(tasks, "base_ref", lambda: None)
    out = tasks.render(tasks.scan_tasks(), reports=tasks.merge_reports(["M1-T3"]))

    assert "재지 못했다" in out
    assert "머지됐는지 확인" not in out


# ------------------------------------------- base 가 낡았다고 미리 말해 주는지


def test_a_fresh_base_says_nothing():
    """앞서 있지 않으면 아무 말도 안 한다. 늘 뜨는 경고는 안 읽힌다."""
    assert tasks.stale_message("origin/main", 0) is None
    assert tasks.stale_message("origin/main", -1) is None


def test_a_stale_base_says_how_far_and_what_to_do():
    """충돌을 본 **뒤**가 아니라 일을 시작하기 **전**에 말해 줘야 쓸모가 있다."""
    message = tasks.stale_message("origin/main", 3)

    assert message is not None
    assert "3커밋" in message
    assert "git merge origin/main" in message
    # 왜 합쳐야 하는지까지 말한다. 이유를 모르면 그냥 넘긴다.
    assert "충돌" in message


def test_the_stale_warning_is_shown_above_the_open_list(repo):
    out = tasks.render(tasks.scan_tasks(), reports={tasks._BASE_KEY: "base 가 낡았다"})

    assert "base 가 낡았다" in out
    assert out.index("base 가 낡았다") < out.index("열린 작업")


def test_this_repository_can_be_asked_how_far_behind_it_is():
    """순수 함수가 맞아도 git 을 못 읽으면 장치는 조용히 꺼진다."""
    # 앞서 있든 아니든 예외 없이 답해야 한다. 값 자체는 저장소 상태에 따라 달라진다.
    assert tasks.behind_base() is None or isinstance(tasks.behind_base(), str)
