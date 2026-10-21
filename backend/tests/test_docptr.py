"""문서 → 코드 포인터 도구가 약속한 것을 지키는지 본다.

가장 중요한 약속은 **줄이 밀려도 길을 잃지 않는다**는 것이다. 주소가 qualname 이라
코드를 위아래로 옮겨도 그대로 풀려야 하고, 이름이 바뀌면 그때는 실패해야 한다.
"""

from __future__ import annotations

import pytest

from tools import docptr


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """documents/ 와 소스 한 벌을 가진 가짜 저장소."""
    (tmp_path / "documents" / "plan").mkdir(parents=True)
    (tmp_path / "pkg").mkdir()
    monkeypatch.setattr(docptr, "ROOT", tmp_path)
    monkeypatch.setattr(docptr, "DOCS", tmp_path / "documents")
    return tmp_path


def write(path, text: str) -> None:
    path.write_text(text.lstrip("\n"), encoding="utf-8")


SOURCE = '''
"""모듈 설명."""

VALUE = 1


class Thing:
    """클래스 설명."""

    def run(self) -> None:
        """메서드 설명."""


def top() -> None:
    """함수 설명."""
'''


def test_addresses_resolve_to_symbols_not_lines(repo):
    table = docptr.symbols_of(SOURCE)
    assert set(table) == {None, "Thing", "Thing.run", "top"}


def test_a_pointer_survives_the_code_moving_down(repo):
    """줄 번호였다면 전부 어긋났을 변경 — import 를 열 줄 끼워 넣는다."""
    write(repo / "documents" / "01.md", "# 1. 문서\n\n`→ pkg/m.py::Thing.run`\n")
    write(repo / "pkg" / "m.py", SOURCE)
    assert docptr.run(write=True) == 0
    before = (repo / "pkg" / "m.py").read_text()

    write(repo / "pkg" / "m.py", "import os\n" * 10 + before)
    assert docptr.run(write=False) == 0, "줄만 밀렸는데 포인터가 길을 잃었다"


def test_renaming_the_symbol_fails_loudly(repo, capsys):
    write(repo / "documents" / "01.md", "# 1. 문서\n\n`→ pkg/m.py::Thing.run`\n")
    write(repo / "pkg" / "m.py", SOURCE.replace("def run", "def execute"))
    assert docptr.run(write=False) == 1
    assert "`Thing.run` 이 없다" in capsys.readouterr().err


def test_the_marker_lands_at_the_end_of_the_docstring(repo):
    write(repo / "documents" / "guide.md", "# 9. 문서\n\n## 3.1 어떤 절\n\n`→ pkg/m.py::top`\n")
    write(repo / "pkg" / "m.py", SOURCE)
    docptr.run(write=True)
    assert '"""함수 설명.\n\n    [문서] guide.md §3.1\n    """' in (repo / "pkg" / "m.py").read_text()


def test_a_plan_tag_is_used_as_the_label(repo):
    write(repo / "documents" / "plan" / "ISSUES.md", "# 이슈\n\n- [ ] H-012  무엇\n  `→ pkg/m.py::top`\n")
    write(repo / "pkg" / "m.py", SOURCE)
    docptr.run(write=True)
    assert "[문서] plan/ISSUES.md H-012" in (repo / "pkg" / "m.py").read_text()


def test_writing_twice_changes_nothing(repo):
    write(repo / "documents" / "01.md", "# 1. 문서\n\n`→ pkg/m.py::top`\n")
    write(repo / "pkg" / "m.py", SOURCE)
    docptr.run(write=True)
    once = (repo / "pkg" / "m.py").read_text()
    assert docptr.run(write=True) == 0
    assert (repo / "pkg" / "m.py").read_text() == once


def test_check_mode_fails_while_the_code_is_out_of_date(repo):
    write(repo / "documents" / "01.md", "# 1. 문서\n\n`→ pkg/m.py::top`\n")
    write(repo / "pkg" / "m.py", SOURCE)
    assert docptr.run(write=False) == 1, "갱신이 필요한데 통과했다"
    docptr.run(write=True)
    assert docptr.run(write=False) == 0


def test_a_marker_is_removed_when_the_document_stops_pointing(repo):
    doc = repo / "documents" / "01.md"
    write(doc, "# 1. 문서\n\n`→ pkg/m.py::top`\n")
    write(repo / "pkg" / "m.py", SOURCE)
    docptr.run(write=True)
    assert docptr.MARKER in (repo / "pkg" / "m.py").read_text()

    # 코드 쪽은 생성물이므로 문서가 손을 떼면 따라 사라진다. 손으로 지울 일이 없다.
    write(doc, "# 1. 문서\n\n이제 아무것도 가리키지 않는다.\n")
    assert docptr.run(write=True) == 0
    assert docptr.MARKER not in (repo / "pkg" / "m.py").read_text()


def test_a_symbol_without_a_docstring_gets_one(repo):
    write(repo / "documents" / "01.md", "# 1. 문서\n\n`→ pkg/m.py::bare`\n")
    write(repo / "pkg" / "m.py", "def bare() -> None:\n    return None\n")
    docptr.run(write=True)
    assert '    """[문서] 01.md §1"""' in (repo / "pkg" / "m.py").read_text()


def test_examples_inside_code_blocks_are_not_pointers(repo):
    """규약을 설명하는 문서가 자기 예시를 가리키면 안 된다."""
    write(
        repo / "documents" / "01.md",
        "# 1. 문서\n\n이렇게 적는다:\n\n```\n`\u2192 pkg/m.py::top`\n```\n",
    )
    write(repo / "pkg" / "m.py", SOURCE)
    assert docptr.run(write=True) == 0
    assert docptr.MARKER not in (repo / "pkg" / "m.py").read_text()


def test_creating_a_docstring_converges_in_one_write(repo):
    """만드는 모양과 고치는 모양이 다르면 `--write` 가 한 번에 끝나지 않는다.

    실제로 그랬다 — 없던 docstring 은 세 줄로 만들고 있던 것은 두 줄로 고쳐서,
    쓰고 나서도 검사가 계속 빨갰다 (H-020).
    """
    write(repo / "documents" / "01.md", "# 1. 문서\n\n`→ pkg/m.py::bare`\n")
    write(repo / "pkg" / "m.py", "def bare() -> None:\n    return None\n")

    assert docptr.run(write=True) == 0
    assert docptr.run(write=False) == 0, "한 번 썼는데 아직 갱신이 필요하다고 한다"
