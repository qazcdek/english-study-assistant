"""기록 정리. 규약은 app/services/history.py 와 03-api-spec.md.

**지우는 일이므로 묶는 규칙이 전부다.** 너무 묶으면 다른 기록이 사라지고,
덜 묶으면 정리가 안 된다. 사용자가 정한 규칙은 하나다 —
**공백 문자를 다 지운 결과가 같으면 중복.**
"""

import pytest

from app.services.history import same_paragraph

PARAGRAPH = "The cat sat on the mat."


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (PARAGRAPH, f"  {PARAGRAPH}  "),
        (PARAGRAPH, PARAGRAPH + "\n"),
        ("The cat sat\n  on the mat.", PARAGRAPH),
        ("The cat sat\n\non the\tmat.", PARAGRAPH),
    ],
    ids=["앞뒤 공백", "끝 줄바꿈", "줄바꿈 위치", "탭과 빈 줄"],
)
def test_whitespace_never_makes_two_paragraphs(a, b):
    """공백은 문단의 내용이 아니다. 다시 붙여 넣을 때 가장 흔히 달라지는 것이다."""
    assert same_paragraph(a) == same_paragraph(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (PARAGRAPH, "the cat sat on the mat."),
        (PARAGRAPH, "The cat sat on the mat"),
        (PARAGRAPH, "A cat sat on the mat."),
    ],
    ids=["대소문자", "마침표", "낱말"],
)
def test_anything_but_whitespace_keeps_them_apart(a, b):
    """**지우는 일에서는 덜 묶는 쪽이 안전하다.**

    대소문자와 문장부호는 영어 학습에서 공부의 대상이다. 묶어 버리면 지우는 쪽이 틀린다.
    """
    assert same_paragraph(a) != same_paragraph(b)


# ------------------------------------------------------- 무엇이 남나


def test_the_newest_survives(both_modes):
    """**최신 하나만 남는다.** 그게 사용자에게 약속한 문구다."""
    api = both_modes
    for _ in range(3):
        api.client.post("/api/analyze", json={"text": PARAGRAPH})
    before = api.client.get("/api/history").json()
    newest = before[0]["id"]
    assert len(before) == 3

    removed = api.client.post("/api/history/tidy").json()["removed"]

    after = api.client.get("/api/history").json()
    assert removed == 2
    assert [r["id"] for r in after] == [newest]


def test_records_that_only_differ_in_whitespace_are_duplicates(both_modes):
    api = both_modes
    api.client.post("/api/analyze", json={"text": PARAGRAPH})
    api.client.post("/api/analyze", json={"text": "The cat sat\n  on the mat."})

    assert api.client.post("/api/history/tidy").json()["removed"] == 1
    assert len(api.client.get("/api/history").json()) == 1


def test_different_paragraphs_are_left_alone(both_modes):
    """정리가 **다른 기록을 지우면** 돌이킬 수 없다."""
    api = both_modes
    api.client.post("/api/analyze", json={"text": PARAGRAPH})
    api.client.post("/api/analyze", json={"text": "A dog sat on the mat."})

    assert api.client.post("/api/history/tidy").json()["removed"] == 0
    assert len(api.client.get("/api/history").json()) == 2


def test_tidying_with_nothing_to_tidy_is_quiet(both_modes):
    """누를 때마다 뭔가 지워지는 것처럼 보이면 안 된다."""
    api = both_modes
    api.client.post("/api/analyze", json={"text": PARAGRAPH})

    assert api.client.post("/api/history/tidy").json()["removed"] == 0
    assert api.client.post("/api/history/tidy").json()["removed"] == 0


def test_the_count_matches_what_tidying_removes(both_modes):
    """화면이 **묻기 전에** 이 숫자를 보여준다. 실제와 다르면 거짓말이 된다."""
    api = both_modes
    for _ in range(3):
        api.client.post("/api/analyze", json={"text": PARAGRAPH})
    api.client.post("/api/analyze", json={"text": "A dog sat on the mat."})

    counted = api.client.get("/api/history/duplicates").json()["removed"]
    removed = api.client.post("/api/history/tidy").json()["removed"]

    assert counted == removed == 2
