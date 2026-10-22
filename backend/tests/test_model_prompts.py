"""모델 계열별 프롬프트. 규약은 04-prompt-design.md §9.

가르는 선이 이 검사의 전부다 —
**교육 내용은 한 곳, 길들이기는 계열별.** 교육 내용이 계열별 파일로 새어 들어오면
계열마다 복사되고, 그때부터 조용히 갈라진다.
"""

import pytest

from app.prompts import models
from app.prompts.analysis import PART_SPECS, build_messages
from app.prompts.models import VARIANTS, family_of, variant_for

FAMILIES = (models.GEMINI, models.LLAMA, models.OPENAI, models.CLAUDE, models.UNKNOWN)


def test_every_family_has_a_variant():
    """빠진 계열이 있으면 `variant_for` 가 KeyError 로 터진다 — 조용히 넘기지 않는다."""
    assert set(VARIANTS) == set(FAMILIES)


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("gemini-3.5-flash-lite", models.GEMINI),
        ("gemini-4", models.GEMINI),
        ("claude-opus-5-5", models.CLAUDE),
        ("gpt-5", models.OPENAI),
        ("o3-mini", models.OPENAI),
        ("qwen3.8-27b", models.LLAMA),
        ("local-model", models.LLAMA),
        ("", models.UNKNOWN),
        ("무엇인지-모를-모델", models.UNKNOWN),
    ],
)
def test_the_family_is_read_from_the_name(model, family):
    """**버전이 아니라 계열로 가른다.** 버전마다 키를 두면 모델을 올릴 때 조용히 기본값으로 떨어진다."""
    assert family_of(model) == family


def test_an_unknown_model_falls_back_without_guessing():
    """모르는 모델에 다른 모델용 처방을 끼얹지 않는다."""
    assert variant_for("무엇인지-모를-모델") is VARIANTS[models.UNKNOWN]


# ------------------------------------------------- 지금은 네 계열이 같다


@pytest.mark.parametrize("field", ("output_rules", "practice_rules", "retry_nudge"))
def test_all_families_share_the_same_wording_for_now(field):
    """**갈라짐은 사고가 아니라 결정으로만 일어나야 한다.**

    사용자가 "일단 동일한 프롬프트를 쓰되 구조만 만들어 둔다" 고 정했다. 그래서 지금은
    같고, 같다는 것을 여기서 고정한다. 실측(M3-T1)이 차이를 보여주면 **이 검사를
    고치면서** 갈린다 — 검사를 고치는 일이 곧 결정의 기록이다.
    """
    wordings = {getattr(variant, field) for variant in VARIANTS.values()}

    assert len(wordings) == 1, f"{field} 가 계열마다 다르다. 실측 근거가 있다면 이 검사를 고친다"


# ------------------------------------------------- 교육 내용은 새어 들어오지 않는다

# 계열별 파일에 있으면 안 되는 교육 낱말. 있으면 계열마다 복사된다.
TEACHING = ("표현 유형", "관용구", "Phrasal Verb", "초급", "중급", "고급", "비합성")


def test_teaching_content_stays_out_of_the_per_family_wording():
    """교육 내용이 계열별 지시문에 들어가면 계열마다 복사되고, 그때부터 갈라진다 (11 §2.1).

    **파일 글자가 아니라 실제로 프롬프트에 실리는 문구를 본다.** 처음에는 파일을
    훑었는데, "교육 내용을 여기 적지 않는다" 고 적은 **제 설명 주석**이 걸렸다.
    주석은 모델에 가지 않으므로 볼 대상이 아니다.
    """
    found = sorted(
        f"{variant.family}.{field}: {word}"
        for variant in VARIANTS.values()
        for field in ("output_rules", "practice_rules", "retry_nudge")
        for word in TEACHING
        if word in getattr(variant, field)
    )
    assert not found, f"교육 내용이 계열별 지시문에 들어왔다: {found}"


# ------------------------------------------------- 실제로 프롬프트에 실리나


def test_the_variant_wording_is_actually_used():
    """묶음을 만들어 두고 안 쓰면 아무 일도 안 일어난다."""
    spec = PART_SPECS[0]
    system = build_messages(spec, "hello world", model="gemini-3.5-flash-lite")[0].content

    assert VARIANTS[models.GEMINI].output_rules in system


def test_the_retry_nudge_comes_from_the_variant():
    spec = PART_SPECS[0]
    plain = build_messages(spec, "hello world", model="gpt-5")[0].content
    retried = build_messages(spec, "hello world", model="gpt-5", retry=True)[0].content

    assert VARIANTS[models.OPENAI].retry_nudge not in plain
    assert VARIANTS[models.OPENAI].retry_nudge in retried


def test_the_teaching_part_does_not_depend_on_the_model():
    """교육 내용은 계열과 무관하게 한 벌이다. 지금은 길들이기도 같으므로 전체가 같다."""
    spec = PART_SPECS[1]  # 표현 풀이 — 교육 내용이 가장 많은 파트
    for model in ("gemini-3.5-flash-lite", "claude-opus-5-5", "qwen3.8-27b", ""):
        built = build_messages(spec, "hello world", model=model)[0].content
        assert "Phrasal Verb" in built, model


def test_practice_prompt_takes_the_variant_too():
    from app.prompts import practice

    system = practice.build_messages(
        expression="sum up",
        meaning="요약하다",
        prompt_ko="요점을 요약해 보겠습니다.",
        model_answer="Let me sum up the main points.",
        learner_answer="Let me sum up main points.",
        model="claude-opus-5-5",
    )[0].content

    assert VARIANTS[models.CLAUDE].practice_rules in system
