"""회원별 저장 데이터.

로컬 모드에서는 쓰이지 않는다. 웹 배포(cloud) 모드에서만 만들어진다.
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
