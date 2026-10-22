"""고를 수 있는 제공자 목록. 규약은 09-mode-matrix.md §3.2.

제공자가 늘면 **다섯 곳이 함께 늘어난다** — 구현 · 키 저장 · 프롬프트 계열 ·
선택 UI · **개인정보처리방침의 국외 이전 수탁자**. 목록이 흩어지면 하나를 빼먹고,
빼먹은 것이 방침이면 **적지 않은 곳으로 데이터가 나간다.**

그래서 이 검사는 목록과 나머지를 **대조한다.**
"""

import pytest

from app.prompts import models as families
from app.providers import registry

MODES = ("local", "cloud")


def test_the_registry_is_not_empty():
    """빈 목록을 훑으면 아래 검사들이 통과만 한다."""
    assert len(registry.PROVIDERS) >= 4


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_can_choose_something(mode):
    """고를 것이 없으면 그 모드는 아무것도 못 한다."""
    assert registry.selectable(mode)
    assert registry.default_for(mode).implemented


def test_llama_server_is_local_only():
    """내 PC 에 있는 서버다. Render 에서 닿지 않는다 (09 §3.2)."""
    ids = {p.id for p in registry.selectable("cloud")}

    assert registry.LLAMA not in ids
    assert registry.LLAMA in {p.id for p in registry.selectable("local")}


def test_local_can_choose_cloud_models_too():
    """사용자가 정한 규칙이다 — local 은 llama-server **와** cloud LLM 전부."""
    ids = {p.id for p in registry.selectable("local")}

    assert registry.GEMINI in ids, "local 에서 Gemini 를 고를 수 있어야 한다"
    assert len(ids) >= 2


@pytest.mark.parametrize("mode", MODES)
def test_only_working_providers_are_selectable(mode):
    """**고를 수 있는데 안 되는 것은 목록에 없는 것보다 나쁘다.**"""
    assert all(p.implemented for p in registry.selectable(mode))


def test_what_is_not_implemented_says_why():
    """비워 두면 다음 사람이 같은 조사를 다시 한다."""
    missing = [p.id for p in registry.PROVIDERS if not p.implemented and not p.note]

    assert not missing, f"왜 안 되는지 안 적혀 있다: {missing}"


def test_every_provider_offers_at_least_one_model():
    """모델 목록의 첫 번째가 기본값이다. 비면 기본값이 없다."""
    assert all(p.models for p in registry.PROVIDERS)


def test_a_key_is_required_unless_the_server_is_mine():
    """내 PC 의 llama-server 만 키가 없다. 나머지는 회원 키로 호출한다."""
    for provider in registry.PROVIDERS:
        assert provider.needs_key is not provider.local_only, provider.id


def test_a_provider_that_needs_a_key_tells_where_to_get_it():
    """회원이 키를 어디서 받는지 모르면 등록할 수 없다."""
    missing = [p.id for p in registry.PROVIDERS if p.needs_key and not p.key_url]

    assert not missing, f"키 발급 주소가 없다: {missing}"


def test_every_model_name_maps_to_a_prompt_family():
    """**프롬프트 계열을 못 알아보면 조용히 기본 문구로 떨어진다** (04 §9.3).

    새 모델을 목록에 더하면서 `prompts/models.py` 의 표를 안 고치는 것이 가장
    잡기 어려운 어긋남이다 — 아무것도 깨지지 않고 길들이기만 사라진다.
    """
    unmapped = [
        (provider.id, model)
        for provider in registry.PROVIDERS
        for model in provider.models
        if families.family_of(model) == families.UNKNOWN
    ]

    assert not unmapped, f"계열을 못 알아보는 모델: {unmapped}"


def test_ids_are_unique():
    ids = [p.id for p in registry.PROVIDERS]

    assert len(ids) == len(set(ids))
    assert set(registry.BY_ID) == set(ids)


def test_an_unknown_id_is_not_guessed():
    assert registry.info("있을-리-없는-제공자") is None


def test_each_implementation_belongs_to_its_provider():
    """구현 표의 클래스가 **그 제공자의 것**인지 본다.

    `implemented` 를 선언에서 구현 표로 옮기고 나서도, 엉뚱한 클래스를 매달면
    여전히 통과했다 — `anthropic: GeminiProvider` 로 바꿔 봤더니 46개가 다 통과했다.
    그래서 모듈명이나 클래스명이 제공자 id 를 담고 있는지 대조한다.

    **이름만 본다.** `AnthropicProvider` 라는 이름으로 Gemini 를 부르는 구현은 못 잡는다.
    거기까지가 기계로 닿는 선이다 (10 §6).
    """
    mismatched = []
    for provider_id, implementation in registry.IMPLEMENTATIONS.items():
        where = f"{implementation.__module__}.{implementation.__name__}".lower()
        # llama 는 모듈이 `llama_server` 다. id 가 담겨 있으면 된다.
        if provider_id not in where:
            mismatched.append(f"{provider_id} → {implementation.__name__}")

    assert not mismatched, f"제공자와 구현이 안 맞는다: {mismatched}"


def test_every_implementation_has_an_entry():
    """구현만 있고 목록에 없으면 아무도 고를 수 없다 — 만들어 두고 잊은 것이다."""
    orphans = sorted(set(registry.IMPLEMENTATIONS) - set(registry.BY_ID))

    assert not orphans, f"구현은 있는데 목록에 없다: {orphans}"
