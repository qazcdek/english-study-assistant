"""문단으로 묶는다 (M13-T11).

규약은 `app/services/paragraphs.py` 와 `app/services/grouping.py` 머리말.
여기서 지키는 것은 넷이다.

- **본문이 바뀌지 않는다** — 번호를 받아 원문에서 이어 붙인다
- **못 믿을 경계는 버린다** — 단어 예산 묶기로 떨어진다
- **실패가 글감을 없애지 않는다** — 주제 경계는 없어도 되는 것이다
- **꼬리의 `…` 는 버린 토막이 있을 때만** — 추측하지 않는다
"""

import json

import pytest

from app.providers.base import ChatMessage, CompletionResult, LLMProvider
from app.providers.schema import SchemaLimits
from app.services import grouping, paragraphs


def para(words: int, mark: str) -> str:
    return " ".join([mark] * words)


class FakeBoundaries(LLMProvider):
    """`starts` 를 정해 둔 대로 돌려주는 프로바이더. 문자열이면 그대로 내보낸다."""

    model = "fake"
    # **기본값을 그대로 쓴다.** `None` 을 뒀더니 `adapt()` 가 터져 넓은 `except` 에
    # 걸려 **전부 단어 예산으로 떨어졌다** — `base.py` 가 "가짜가 진짜보다 좁으면
    # 멀쩡한 제약이 조용히 사라진다" 고 경고해 둔 자리다.
    schema_limits = SchemaLimits()

    def __init__(self, reply: object) -> None:
        self.reply = reply
        self.calls = 0

    async def complete(self, messages, **kw) -> CompletionResult:
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        text = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
        return CompletionResult(text=text, model=self.model)

    async def aclose(self) -> None:
        pass

    async def health(self):
        return None


# ------------------------------------------------- 단어 예산 묶기 (떨어질 자리)


def test_short_pieces_are_joined_up_to_the_budget():
    """가디언 `<p>` 는 **절반 이상이 한 문장**이다. 그대로 두면 한 문장에 네 번 부른다."""
    texts = [para(40, "a"), para(40, "b"), para(60, "c"), para(10, "d")]

    assert paragraphs.group(texts, budget=100) == [[0, 1], [2, 3]]


def test_a_piece_longer_than_the_budget_stands_alone_without_being_split():
    """쪼개면 문장이 끊긴다. 실측 최댓값이 1,021자라 입력 상한 안이다."""
    texts = [para(200, "big"), para(10, "small")]

    assert paragraphs.group(texts, budget=100) == [[0], [1]]


def test_joining_uses_the_source_text_and_changes_nothing():
    """**번호를 받는 이유가 이것이다.** 글을 받으면 한 글자가 달라졌는지 알 수 없다."""
    texts = ["First piece.", "Second piece.", "Third piece."]

    joined = paragraphs.joined(texts, [[0, 1], [2]])

    assert joined == ["First piece. Second piece.", "Third piece."]


def test_the_ellipsis_marks_that_the_tail_was_dropped():
    """뜻은 "기사가 더 있다" 가 아니라 **"이 문단이 여기서 끊겼을 수 있다"** 다 —
    `<p>` 가 문단이 아니라 문장이므로 진짜 문단 경계를 우리가 모른다."""
    texts = ["One.", "Two."]

    assert paragraphs.joined(texts, [[0, 1]], more=True) == ["One. Two.…"]
    assert paragraphs.joined(texts, [[0, 1]], more=False) == ["One. Two."]


def test_the_ellipsis_does_not_count_as_a_word():
    """**띄우면 상한에 딱 걸린 기사를 다시 앉힐 때 문단이 지워진다** (그 분석까지).
    검사가 451 vs 450 으로 그 자리를 잡았다."""
    texts = [para(500, "w")]

    with_tail = paragraphs.joined(texts, [[0]], more=True)[0]

    assert with_tail.endswith("…")
    assert paragraphs.words(with_tail) == 500


# ------------------------------------------------- 받은 경계를 믿을지


@pytest.mark.parametrize(
    "starts",
    [[1, 3], [0, 3, 3], [0, 5, 2], [0, 99], [0, -1]],
    ids=["0에서-안-시작", "번호가-겹친다", "오름차순이-아니다", "범위-밖", "음수"],
)
def test_boundaries_that_would_lose_or_reorder_text_are_refused(starts):
    texts = [para(10, f"p{i}") for i in range(5)]

    assert grouping.valid(starts, texts) is False


def test_a_group_over_the_ceiling_is_refused():
    """넘으면 **회원 입력 상한과 같은 벽**에 부딪힌다 (cloud 1200자)."""
    texts = [para(grouping.MAX_WORDS, "a"), para(10, "b")]

    assert grouping.valid([0], texts) is False  # 둘이 한 묶음이면 상한 초과
    assert grouping.valid([0, 1], texts) is True


def test_a_sane_boundary_passes():
    texts = [para(30, f"p{i}") for i in range(6)]

    assert grouping.valid([0, 2, 4], texts) is True


def test_spans_have_the_same_shape_as_the_budget_grouping():
    """**같은 모양이어야** 못 믿을 때 그대로 떨어질 수 있다."""
    assert grouping.spans([0, 2, 5], 7) == [[0, 1], [2, 3, 4], [5, 6]]


# ------------------------------------------------- 물어보고 못 믿으면 버린다


async def test_a_usable_boundary_is_used():
    texts = [para(30, f"p{i}") for i in range(6)]
    provider = FakeBoundaries({"starts": [0, 3]})

    assert await grouping.by_topic(texts, provider) == [[0, 1, 2], [3, 4, 5]]
    assert provider.calls == 1


@pytest.mark.parametrize(
    "reply",
    [
        {"starts": [1, 3]},
        {"starts": ["0", "3"]},
        {"starts": []},
        {"nope": [0]},
        "not json at all",
        RuntimeError("연결 실패"),
    ],
    ids=["나쁜-경계", "숫자가-아니다", "비었다", "칸이-없다", "JSON-이-아니다", "호출-실패"],
)
async def test_anything_we_cannot_trust_falls_back_to_the_budget(reply):
    """**이 호출이 터져도 그날 글감이 사라지지 않는다.** 주제 경계는 없어도 되는 것이다."""
    texts = [para(40, f"p{i}") for i in range(6)]

    got = await grouping.by_topic(texts, FakeBoundaries(reply))

    assert got == paragraphs.group(texts)


async def test_without_a_provider_nothing_is_asked():
    """운영자 키가 없는 자리(local)에서 불러도 안전해야 한다."""
    texts = [para(40, f"p{i}") for i in range(4)]

    assert await grouping.by_topic(texts, None) == paragraphs.group(texts)


async def test_a_single_piece_is_not_worth_asking_about():
    """묶을 것이 없는데 호출하면 그냥 낭비다."""
    provider = FakeBoundaries({"starts": [0]})

    await grouping.by_topic(["only one"], provider)

    assert provider.calls == 0


async def test_the_prompt_shows_numbers_and_word_counts_but_asks_for_no_prose():
    """**글을 받으면 본문이 바뀐 줄 모른다.** 번호만 받는다."""
    from app.prompts import grouping as prompts

    messages: list[ChatMessage] = prompts.build_messages(["First one.", "Second one."])
    system, user = messages[0].content, messages[1].content

    assert "글을 쓰지 않는다" in system
    assert "starts" in system
    assert "[0] (2낱말) First one." in user
    assert "[1] (2낱말) Second one." in user
