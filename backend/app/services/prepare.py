"""골라 온 기사를 **문단마다 미리 분석해 둔다** (M13-T5).

회원이 분석을 요청하는 경로(`routers/analyze.py`)와 **같은 분석기를 쓴다.** 다른
것은 세 가지뿐이다 — 누구의 키로 도나, 어디에 저장하나, 누가 부르나.

### 운영자 한 명의 키로 돈다

공용 글감은 누구의 것도 아니지만 만드는 데는 LLM 키가 필요하다. 회원 키를 쓸 수는
없다 — 자기 분석에 쓰라고 등록한 것이다. 그래서 운영자 키로 돌린다
(`services/operator.py` 가 왜 그런지와 플래그가 어떻게 켜지는지를 든다).

**제공자와 모델을 고정한다.** 운영자의 활성 선택을 따르지 않는다 — 운영자가 설정
화면에서 제공자를 바꾸면 모든 회원이 보는 글감 품질이 같이 흔들린다.

### 난이도는 하나다

`paragraph_analyses` 는 난이도마다 행을 따로 둘 수 있지만 **지금은 하나만 채운다.**
값이 안 맞는다 — 기사 한 편 18문단 × 네 파트 = **72 호출**이고 Gemini 무료 등급이
일 250 이다. 셋을 다 채우면 216 이 되어 한 편으로 하루가 끝난다. 영·미 두 곳을
올리려면(144) 하나여야 한다 (M13-T1 · M13-T3 실측).

### 사용량을 세지 않는다

`usage.check_and_increment` 는 **회원 각자의 하루 한도**다 (09 §3.3). 여기는 회원
요청이 아니라 서버 일이므로 세지 않는다. 세면 글감을 한 번 만든 날 운영자가 자기
계정으로 아무것도 못 한다 — 글감 때문에 한도를 다 쓴 것이 된다.

대신 **양이 저절로 막혀 있다.** 한 번에 기사 한 편이고 문단 수만큼만 돈다.

### 문단마다 커밋한다

기사 한 편이 72 호출이라 몇 분이 걸린다. 끝에 한 번 커밋하면 중간에 죽을 때
**그때까지 쓴 호출이 전부 버려진다.** 문단마다 커밋해 두면 다시 돌릴 때 이미 된
것을 건너뛴다.

### 재시도는 upsert 다

**`failed_parts` 가 비어 있지 않으면 재시도 대상이다.** 네 파트 중 일부만 실패한
문단은 행을 남기되(살아난 파트는 보여줄 수 있다) 다음에 다시 돌린다. 그때
행을 또 만들지 않고 **같은 행을 덮어쓴다** — `(paragraph_id, level)` 이 유일하므로
새로 넣으면 제약에 걸린다 (M13-T4 의 결정).

### 네 파트가 전부 실패하면 **멈춘다**

한 문단의 파트가 전부 실패하는 것은 **문단 탓이 아니다.** 키가 한도에 걸렸거나
제공자가 죽은 것이고, 남은 17문단을 더 때려도 같은 결과다. 그 자리에서 멈추고
어디서 멈췄는지를 돌려준다 — 다시 돌리면 거기서부터 이어진다.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.auth.crypto import KeyCipher
from app.config import Settings
from app.db import Article, ArticleParagraph, ParagraphAnalysis
from app.errors import LLMError, OperatorKeyRequiredError
from app.providers import registry
from app.schemas import AnalyzeRequest, AnalyzeResponse, Level
from app.services import keys, operator, records
from app.services.analyzer import AnalyzerService

# 미리 분석해 두는 난이도. **하나뿐이다** — 왜인지는 머리말.
JOB_LEVEL: Level = "intermediate"


@dataclass
class Report:
    """한 번 돌린 결과.

    **숫자를 나눠 센다.** 합계 하나로는 "다 됐다" 와 "다 건너뛰었다" 가 구별되지
    않는다 — 키가 죽어 아무것도 못 했는데 성공처럼 보이는 쪽이 가장 나쁘다.
    """

    prepared: int = 0
    """새로 채운 문단."""
    retried: int = 0
    """전에 일부 실패했던 것을 다시 돌려 덮어쓴 문단."""
    skipped: int = 0
    """이미 온전해서 건드리지 않은 문단."""
    partial: int = 0
    """돌렸지만 일부 파트가 **또** 실패한 문단. `prepared`·`retried` 에도 센다."""
    stopped_at: int | None = None
    """네 파트가 전부 실패해 멈춘 문단의 `ordinal`. 끝까지 갔으면 `None`."""

    @property
    def touched(self) -> int:
        return self.prepared + self.retried


def analyzer_for(db: Session, cipher: KeyCipher, settings: Settings) -> AnalyzerService:
    """운영자 키로 도는 분석기. **회원 키를 쓰지 않는다.**

    운영자가 없거나 그 키가 없으면 여기서 멈춘다 — 빈 키로 호출을 시작하면
    문단마다 한 번씩 실패하면서 72번을 헛돈다.
    """
    owner = operator.find(db)
    if owner is None:
        raise OperatorKeyRequiredError(
            "운영자 계정이 없습니다. 운영자 이메일로 cloud 에 로그인하면 플래그가 켜집니다.",
            detail=f"operator={operator.OPERATOR_EMAIL}",
        )

    api_key = keys.decrypt(db, owner.id, operator.JOB_PROVIDER, cipher)
    if not api_key:
        raise OperatorKeyRequiredError(
            "운영자의 공용 글감용 키가 등록되지 않았습니다. 설정 화면에서 등록해야 합니다.",
            detail=f"provider={operator.JOB_PROVIDER}",
        )

    info = registry.info(operator.JOB_PROVIDER)
    if info is None:  # pragma: no cover - 레지스트리와 함께 바뀐다
        raise OperatorKeyRequiredError(detail=f"목록에 없는 제공자: {operator.JOB_PROVIDER}")

    # **운영자의 활성 선택을 따르지 않는다.** 목록의 기본 모델로 고정한다.
    return AnalyzerService(
        registry.build(info.id, info.models[0], api_key, settings)
    )


async def article(
    db: Session,
    target: Article,
    cipher: KeyCipher,
    settings: Settings,
    *,
    level: Level = JOB_LEVEL,
) -> Report:
    """기사 한 편의 문단을 순서대로 분석해 `paragraph_analyses` 를 채운다.

    이미 온전한 문단은 건너뛰므로 **몇 번 불러도 안전하다.** 그것이 재시도 수단이다.
    """
    report = Report()
    analyzer = analyzer_for(db, cipher, settings)

    try:
        for paragraph in _paragraphs(db, target.id):
            done = _stored(db, paragraph.id, level)
            if done is not None and not done.failed_parts:
                report.skipped += 1
                continue

            try:
                response = await analyzer.analyze(
                    AnalyzeRequest(text=paragraph.text, level=level)
                )
            except LLMError:
                # 네 파트가 전부 실패했다 — 문단 탓이 아니다. 머리말을 본다.
                report.stopped_at = paragraph.ordinal
                break

            _store(db, paragraph.id, level, response)
            db.commit()

            if done is None:
                report.prepared += 1
            else:
                report.retried += 1
            if response.meta.failed_parts:
                report.partial += 1
    finally:
        await analyzer.provider.aclose()

    return report


def _paragraphs(db: Session, article_id: int) -> list[ArticleParagraph]:
    return (
        db.query(ArticleParagraph)
        .filter(ArticleParagraph.article_id == article_id)
        .order_by(ArticleParagraph.ordinal)
        .all()
    )


def _stored(db: Session, paragraph_id: int, level: str) -> ParagraphAnalysis | None:
    return (
        db.query(ParagraphAnalysis)
        .filter(
            ParagraphAnalysis.paragraph_id == paragraph_id,
            ParagraphAnalysis.level == level,
        )
        .one_or_none()
    )


def _store(
    db: Session, paragraph_id: int, level: str, response: AnalyzeResponse
) -> ParagraphAnalysis:
    """있으면 덮어쓰고 없으면 넣는다. `(paragraph_id, level)` 이 유일하다.

    저장 모양을 `AnalysisRecord` 와 맞춘다 — 같은 분석기가 만들고 같은 화면이 읽는다.
    `records.stamp` 도 함께 찍는다. 안 찍으면 읽을 때 형식 올리기가 옛 기록으로 보고
    없는 칸을 채우려 든다.
    """
    row = _stored(db, paragraph_id, level)
    if row is None:
        row = ParagraphAnalysis(paragraph_id=paragraph_id, level=level)
        db.add(row)

    row.result = records.stamp(response.result.model_dump())
    row.markdown = response.markdown.model_dump()
    row.failed_parts = response.meta.failed_parts
    row.model = response.meta.model
    return row
