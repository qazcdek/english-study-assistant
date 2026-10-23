"""고를 수 있는 제공자 목록. 규약은 09-mode-matrix.md §3.2.

제공자가 늘면 **다섯 곳이 함께 늘어난다** — 구현 · 키 저장 · 프롬프트 계열 ·
선택 UI · **개인정보처리방침의 국외 이전 수탁자**. 목록이 흩어지면 하나를 빼먹고,
빼먹은 것이 방침이면 **적지 않은 곳으로 데이터가 나간다.**

그래서 이 검사는 목록과 나머지를 **대조한다.**
"""

from pathlib import Path

import pytest

from app.config import get_settings
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


async def test_every_cloud_provider_can_actually_be_built():
    """**고를 수 있으면 만들어진다.** 목록에 있다는 것으로는 모른다.

    전에는 `deps.py` 가 `if provider_id == GEMINI` 로 하나만 만들고 나머지에
    `RuntimeError` 를 냈다. OpenAI·Anthropic 구현이 들어온 뒤에도 그 분기가 안 늘어서
    **고를 수는 있고 호출은 전부 터지는** 상태로 머지를 넘겼다 (H-034).

    위의 `test_every_implementation_has_an_entry` 는 이걸 못 잡는다 — 목록과 구현 표를
    맞춰 보기만 하고, **만들어 보지는 않는다.** 그래서 실제로 만든다.
    """
    settings = get_settings()

    for provider in registry.selectable("cloud"):
        built = registry.build(provider.id, provider.models[0], "sk-test", settings)
        try:
            assert isinstance(built, registry.IMPLEMENTATIONS[provider.id]), provider.id
            assert built.model == provider.models[0]
        finally:
            await built.aclose()


async def test_the_shared_local_server_is_not_built_here():
    """llama-server 는 생성자 모양이 다르고(주소가 첫 인자) 앱 수명 동안 공유한다.

    키 자리에 주소를 받아 **조용히 엉뚱한 서버로 붙는** 쪽을 막는다.
    """
    with pytest.raises(RuntimeError, match="lifespan"):
        registry.build(registry.LLAMA, "local-model", "", get_settings())


# ------------------------------------------- 방침과 대조한다 (M12-T5)
# 이 파일 머리말이 "다섯 곳을 대조한다" 고 적어 두었으나 **방침만 장치가 없었다.**
# 선언은 있고 장치는 없는 자리가 바로 어긋나는 자리다 (12-tooling.md §6).

PRIVACY = Path(__file__).resolve().parents[2] / "frontend/src/legal/Privacy.tsx"


def privacy_text() -> str:
    return PRIVACY.read_text(encoding="utf-8")


def test_the_privacy_policy_can_actually_be_read():
    """**먼저 이것부터.** 파일을 못 읽으면 아래 검사들이 통과만 한다."""
    assert PRIVACY.exists(), f"{PRIVACY} 가 없다 — 아래 검사가 무의미해진다"
    assert "받는곳" in privacy_text()


@pytest.mark.parametrize("provider", [p for p in registry.PROVIDERS if not p.local_only])
def test_every_cloud_provider_declares_the_name_it_appears_under(provider):
    """밖으로 나가는 제공자는 방침에 적을 이름을 들고 있어야 한다."""
    assert provider.transfer_name, f"{provider.id} 에 transfer_name 이 없다"


def test_a_provider_on_my_own_machine_has_no_transfer_name():
    """llama-server 는 내 PC 다. 나가지 않는 것을 나간다고 적으면 그것도 거짓이다."""
    for provider in registry.PROVIDERS:
        if provider.local_only:
            assert not provider.transfer_name, provider.id


@pytest.mark.parametrize("provider", [p for p in registry.PROVIDERS if not p.local_only])
def test_every_cloud_provider_is_named_in_the_privacy_policy(provider):
    """**고를 수 있는 제공자로 데이터가 나가는데 방침에 없으면 그게 누출이다.**

    목록에만 올리고 구현하지 않은 제공자도 적어 둔다 — 적어 두는 것은 해가 없고,
    구현한 날에 빼먹는 것이 해다.
    """
    assert provider.transfer_name in privacy_text(), (
        f"{provider.id} 가 개인정보처리방침의 국외 이전 표에 없다 — "
        f"`{provider.transfer_name}` 을 {PRIVACY.name} 의 TRANSFERS 에 더한다"
    )
