import json

import pytest
from fastapi.testclient import TestClient

from app.deps import get_provider
from app.errors import LLMBadOutputError
from app.main import create_app
from app.schemas import PracticeRequest
from app.services.practice import PracticeService
from tests.fake_provider import PRACTICE_PAYLOAD, FakeProvider

REQUEST = {
    "expression": "across the pond",
    "meaning": "대서양을 건너",
    "prompt_ko": "그녀의 소설은 마침내 대서양을 건너갔다.",
    "model_answer": "Her novel finally made it across the pond.",
    "learner_answer": "Her novel finally made it across the pond",
}


def request(**overrides) -> PracticeRequest:
    return PracticeRequest(**{**REQUEST, **overrides})


async def test_grade_returns_structured_feedback():
    response = await PracticeService(FakeProvider()).grade(request())

    assert response.result.verdict == "통함"
    assert response.result.uses_target is True
    assert response.result.good_point
    assert response.model_answer == REQUEST["model_answer"]


async def test_other_notes_are_capped():
    """지적이 쏟아지면 학습자가 압도된다. 프롬프트로 막고 코드로도 자른다."""
    response = await PracticeService(FakeProvider()).grade(request())

    assert len(response.result.other_notes) == 2


async def test_corrected_is_dropped_when_identical_to_learner_answer():
    learner = PRACTICE_PAYLOAD["corrected"]
    response = await PracticeService(FakeProvider()).grade(request(learner_answer=learner))

    assert response.result.corrected == ""


async def test_prompt_marks_model_answer_as_one_example_only():
    """모범 답안과 다르다고 틀린 것이 아니라는 점이 프롬프트에 있어야 한다."""
    provider = FakeProvider()
    await PracticeService(provider).grade(request())

    system = provider.calls[0][1][0].content
    user = provider.calls[0][1][1].content
    assert "모범 답안은 하나의 예일 뿐이다" in system
    assert "유일한 정답이 아니다" in user
    assert REQUEST["learner_answer"] in user


async def test_bad_json_raises_after_retry():
    service = PracticeService(FakeProvider({"practice": "깨진 응답"}))

    with pytest.raises(LLMBadOutputError):
        await service.grade(request())


async def test_retry_is_recorded():
    good = json.dumps(PRACTICE_PAYLOAD, ensure_ascii=False)
    service = PracticeService(FakeProvider({"practice": ["깨진 응답", good]}))

    response = await service.grade(request())

    assert response.meta.retried_parts == ["practice"]


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as c:
        yield c


def test_practice_endpoint(client):
    resp = client.post("/api/practice", json=REQUEST)

    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["verdict"] == "통함"
    assert body["model_answer"] == REQUEST["model_answer"]


def test_blank_learner_answer_is_rejected(client):
    resp = client.post("/api/practice", json={**REQUEST, "learner_answer": "   "})
    assert resp.status_code == 422
