"""저장 데이터의 표.

**두 모드가 같은 표를 쓴다.** 로컬도 Postgres 에 쌓고, 앱이 뜰 때 만드는 사용자 행
하나(`id=1`)가 주인이다. 그래서 리비전도 하나다 (14-data-layer.md §2 · 09 §4).

표는 **셋으로 갈린다** — `users`, `user_id` 를 든 표, 그리고 공용 표.
무엇이 어느 쪽인지와 그 이유는 14-data-layer.md.

[문서] plan/DONE.md M13-T2
"""

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    picture: Mapped[str] = mapped_column(String(500), default="")

    # 가입 시 "내 Gemini 키와 사용 한도로 호출된다"에 동의한 시각.
    # 동의 없이는 분석을 시작할 수 없다.
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # 어느 제공자·모델로 일하나. **회원 전역 설정**이고, 바꿔 저장하면 그 뒤의 모든
    # 작업이 그것으로 간다 (09-mode-matrix.md §3.2). 비면 모드별 기본값을 쓴다.
    active_provider: Mapped[str] = mapped_column(String(20), default="")
    active_model: Mapped[str] = mapped_column(String(80), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    analyses: Mapped[list["AnalysisRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    practices: Mapped[list["PracticeRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    vocabulary: Mapped[list["VocabularyItem"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    provider_keys: Mapped[list["ProviderKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def has_consented(self) -> bool:
        return self.consented_at is not None


class AnalysisRecord(Base):
    """분석 히스토리. 기기 간 동기화를 위해 서버에 둔다."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_text: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(20), default="intermediate")
    result: Mapped[dict] = mapped_column(JSON)
    markdown: Mapped[dict] = mapped_column(JSON)
    failed_parts: Mapped[list] = mapped_column(JSON, default=list)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="analyses")


class PracticeRecord(Base):
    """작문 연습 채점 기록. 틀린 표현만 모아 다시 풀기의 토대."""

    __tablename__ = "practices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expression: Mapped[str] = mapped_column(String(200), index=True)
    prompt_ko: Mapped[str] = mapped_column(Text)
    model_answer: Mapped[str] = mapped_column(Text)
    learner_answer: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(20), index=True)
    uses_target: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="practices")


class ProviderKey(Base):
    """제공자별 회원 API 키.

    전에는 `users.encrypted_api_key` 한 칸이었다 — 제공자가 하나였기 때문이다.
    둘 이상을 고를 수 있게 되면서(M12-T1) 한 칸으로는 담을 수 없다.

    **`encrypted` 는 `Text` 다.** 길이를 좁히면 안 된다 — 재 보니 **SQLite 는 길이를
    아예 무시하고 그냥 넣고, Postgres 는 `value too long` 으로 거부한다.**
    그래서 짧은 열은 **테스트를 통과하고 배포 때 깨진다.** 자르는 것이 아니라 터지는
    쪽이지만, 어긋남이 배포본에서만 드러난다는 점은 14-data-layer.md §3.3 과 같다.

    `ENCRYPTION_KEY` 는 절대 교체하지 않는다 — 바꾸면 기존 키를 복호화할 수 없다.
    """

    __tablename__ = "provider_keys"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_key_user_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    encrypted: Mapped[str] = mapped_column(Text)
    # 화면에는 끝 네 자리만 보여준다. 평문은 서버 밖으로 나가지 않는다.
    hint: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="provider_keys")


class VocabularyItem(Base):
    """단어장. 표현 풀이에서 담아 둔 항목."""

    __tablename__ = "vocabulary"
    __table_args__ = (UniqueConstraint("user_id", "expression", name="uq_vocab_user_expression"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expression: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(40), default="")
    meaning: Mapped[str] = mapped_column(Text, default="")
    example: Mapped[str] = mapped_column(Text, default="")
    example_ko: Mapped[str] = mapped_column(Text, default="")
    source_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped[User] = relationship(back_populates="vocabulary")


class UsageCounter(Base):
    """일 단위 사용량. 회원 본인 키를 쓰더라도 오작동으로 한도가 날아가지 않게 막는다."""

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_usage_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    analyses: Mapped[int] = mapped_column(Integer, default=0)
    practices: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)


# ------------------------------------------------------------------ 공용 데이터
#
# **회원 것이 아닌 첫 데이터다.** 지금까지 표는 둘로만 갈렸다 — `users` 와
# `user_id` 를 든 표. 서버가 골라 와 **모든 회원이 같은 것을 보는** 글감은 셋째다.
#
# 공용 표는 `user_id` 를 들지 않는다. 그래서 **"깜빡 빠뜨린 표" 와 생김새가 같다.**
# 그 둘을 가르는 것이 아래 `SHARED` 이고, 적지 않으면 검사가 거부한다.
#
# [문서] 14-data-layer.md §3.7


class Article(Base):
    """서버가 골라 온 기사 한 편.

    **본문을 통째로 들지 않는다.** 문단으로 쪼개 `ArticleParagraph` 에 둔다 —
    분석이 문단마다 붙기 때문이다.

    `source_id` 는 출처가 매긴 식별자다(가디언은 `world/2026/oct/22/...` 꼴).
    URL 을 키로 쓰지 않는 이유는 **같은 기사의 URL 이 바뀔 수 있어서**다.
    """

    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_article_source_id"),
        # **하루에 출처당 한 편.** 영·미 한 곳씩을 같은 날 올리는 모양을 미리 허용한다.
        # 고르지 않은 기사는 `picked_for` 가 비어 있고, 빈 값은 유니크에 걸리지 않는다.
        UniqueConstraint("picked_for", "source", name="uq_article_day_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)
    source_id: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    section: Mapped[str] = mapped_column(String(50), default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # 어느 날짜의 글감으로 골랐나. **비어 있으면 아직 안 고른 후보다.**
    picked_for: Mapped[date | None] = mapped_column(Date, index=True, default=None)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    paragraphs: Mapped[list["ArticleParagraph"]] = relationship(
        back_populates="article", cascade="all, delete-orphan", order_by="ArticleParagraph.ordinal"
    )


class ArticleParagraph(Base):
    """기사의 문단 하나. 분석이 붙는 단위다.

    재 보니 가디언 기사의 `<p>` 문단은 **200~500자**였다 (M13-T1). 회원이 직접 치는
    경로의 입력 제한(local 2000 · cloud 800)은 **여기에 걸리지 않는다** — 미리 분석은
    서버가 돌리므로 그 경로를 타지 않는다.
    """

    __tablename__ = "article_paragraphs"
    __table_args__ = (
        UniqueConstraint("article_id", "ordinal", name="uq_paragraph_article_ordinal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    article: Mapped[Article] = relationship(back_populates="paragraphs")


class ParagraphAnalysis(Base):
    """문단 하나의 미리 분석 결과. 난이도마다 따로 둔다.

    `AnalysisRecord` 와 모양을 맞춘다 — 같은 분석기가 만들고 같은 화면이 읽는다.
    다른 점은 `user_id` 가 없다는 것뿐이다.
    """

    __tablename__ = "paragraph_analyses"
    __table_args__ = (
        UniqueConstraint("paragraph_id", "level", name="uq_analysis_paragraph_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    paragraph_id: Mapped[int] = mapped_column(
        ForeignKey("article_paragraphs.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(20), default="intermediate")
    result: Mapped[dict] = mapped_column(JSON)
    markdown: Mapped[dict] = mapped_column(JSON)
    failed_parts: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    paragraph: Mapped[ArticleParagraph] = relationship()


# 공용 표의 목록. **`user_id` 가 없어도 되는 표는 여기 적힌 것뿐이다.**
# 새 표가 여기에도 없고 `user_id` 도 없으면 검사가 거부한다 — 일부러 공용인 것과
# 회원 소유로 만들려다 `user_id` 를 빠뜨린 것을 **생김새로는 구별할 수 없어서**다.
SHARED = (Article, ArticleParagraph, ParagraphAnalysis)
