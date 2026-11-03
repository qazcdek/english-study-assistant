"""손으로 뉴스 한 편을 넣고, 그 자리에서 미리 분석을 돌린다 — `./dev.sh article`.

**자동 선정이 아니다.** 가디언에서 고르고 쿨다운을 다루는 쪽은 `M13-T4` 이고,
이 도구는 그 전에 **눈으로 볼 것을 먼저 만드는 자리**다. `M13` 은 넣기(T4) ·
미리 분석(T5) · 화면(T6) 셋인데 넣기가 제일 크다. 그것이 끝나기를 기다리면
분석과 화면을 **한 번도 실제 데이터로 보지 못한 채** 만들게 된다.

### 넣는 것과 분석하는 것을 가른다

`--prepare` 가 없으면 문단만 앉히고 끝낸다. 기사 한 편이 **문단 수 × 네 파트**
호출이라(16문단이면 64번) 실수로 돌면 운영자 키의 무료 등급을 그냥 쓴다.
그래서 비싼 쪽은 **일부러 따로** 켜야 한다.

### 셸이 환경 파일을 열지 않는다

`--env-file` 을 받아 **파이썬이 직접 읽는다.** bash 로 `source` 하면 셸이 비밀값을
들게 되고, 그 뒤 아무 명령의 출력에나 섞여 나올 수 있다 — 실제로 bash 의 완료된
백그라운드 작업 보고가 DB 연결 문자열을 찍은 적이 있다. `dev.sh` 가 uvicorn 에
`--env-file` 을 넘기는 것과 같은 이유다 (H-044 와 같은 성질의 조심).

### 입력 모양

JSON 하나다. `body` 는 **본문 HTML** 이고 쪼개기(`services/paragraphs.py`)를 그대로
탄다 — 평문을 넣으면 `<p>` 가 없어서 거부된다. 그게 맞다: 자동 경로가 먹을 것과
같은 것을 먹여야 손으로 확인한 결과를 믿을 수 있다.

```json
{
  "source": "guardian",
  "source_id": "world/2026/nov/01/...",
  "url": "https://www.theguardian.com/...",
  "title": "...",
  "byline": "Luke Harding in Kyiv",
  "section": "world",
  "published_at": "2026-11-01T17:20:18Z",
  "body": "<p>...</p><p>...</p>"
}
```

[문서] plan/DONE.md M13-T8
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # `python tools/article.py` 로도 돌 수 있게
    sys.path.insert(0, str(ROOT))

# **`byline` 도 필수다** — 출처 약관이 기자 크레딧을 요구하므로(M13-T10) 빈 칸으로
# 앉히는 길을 두지 않는다. 가디언은 `show-fields=byline` 으로 준다 (열 편 중 열 편).
FIELDS = (
    "source",
    "source_id",
    "url",
    "title",
    "byline",
    "section",
    "published_at",
    "body",
)


def load_env(path: Path) -> None:
    """환경 파일을 **이 프로세스의 환경변수로** 읽는다. 셸을 거치지 않는다.

    이미 들어 있는 값은 덮지 않는다 — 명령줄에서 하나만 바꿔 끼울 수 있어야 한다.
    """
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep:
            os.environ.setdefault(key.strip(), value.strip())


def read_draft(path: Path):
    """JSON 하나를 `Draft` 로. **빠진 칸을 한꺼번에 알려준다** — 하나씩 고치게 하면
    같은 명령을 여섯 번 다시 치게 된다.
    """
    from app.services.articles import Draft

    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [name for name in FIELDS if not data.get(name)]
    if missing:
        raise SystemExit(f"{path} 에 빠진 칸: {', '.join(missing)}")

    # **`Z` 를 손으로 바꾸지 않는다.** 파이썬 3.11 부터 `fromisoformat` 이 그대로
    # 받는다 (이 저장소는 3.11 이상을 요구한다). 바꿔 주는 한 줄을 뒀더니
    # **지워도 검사가 통과했다** — 아무것도 하지 않는 줄이었다.
    return Draft(
        source=data["source"],
        source_id=data["source_id"],
        url=data["url"],
        title=data["title"],
        byline=data["byline"],
        section=data["section"],
        published_at=datetime.fromisoformat(data["published_at"]),
        body=data["body"],
    )


def pick_date(arg: str, today: Callable[[], date]) -> date | None:
    """`--pick` 값을 날짜로. `none` 이면 후보로만 둔다는 뜻이라 `None`.

    **"오늘" 을 여기서 세지 않고 받는다** (`daily.today` — 한국 날짜다). 전에는
    이 자리에서 UTC 로 셌고, 그래서 **한국 시간 11월 2일에 넣은 기사가 11월 1일
    뉴스로 찍혔다.** 자동 선정과 같은 답이 나와야 하므로 두 곳에 적지 않는다.

    `main()` 안에 두면 검사가 **환경 파일과 DB 를 세워야만** 물을 수 있어서 밖으로
    꺼냈다.
    """
    if arg == "none":
        return None
    if arg == "today":
        return today()
    return date.fromisoformat(arg)


def cut_notes(skipped: int, trimmed: int, limit: int) -> list[str]:
    """약관 상한(`M13-T9`)이 한 일을 말로 옮긴다. 한 일이 없으면 빈 목록.

    **조용히 자르면 안 된다.** 16문단짜리 기사를 넣었는데 11문단이 되는 것은 눈으로
    보고 넘어갈 일이고, 지운 쪽은 **분석까지 사라진다.** `main()` 안에 두면 검사가
    출력을 떠야만 물을 수 있어서 밖으로 꺼냈다.
    """
    notes = []
    if skipped:
        notes.append(f"약관 상한({limit}단어)을 넘겨 {skipped}문단 안 썼다")
    if trimmed:
        notes.append(f"이미 들어 있던 {trimmed}문단을 지웠다 — 그 분석도 함께 사라졌다")
    return notes


def where(database_url: str) -> str:
    """어느 DB 인지 **비밀값 없이** 한 줄로. 자격증명은 `@` 앞에 있다."""
    return database_url.rsplit("@", 1)[-1] if "@" in database_url else database_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="뉴스 한 편을 손으로 넣는다 (M13-T8)")
    parser.add_argument("path", type=Path, help="기사 JSON")
    parser.add_argument("--env-file", type=Path, required=True, help="읽을 환경 파일")
    parser.add_argument(
        "--pick",
        metavar="YYYY-MM-DD",
        default="today",
        help="어느 날의 뉴스로 둘지. 기본은 오늘. `none` 이면 후보로만 둔다",
    )
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="넣은 뒤 미리 분석까지 돌린다 — **운영자 키로 문단 수 × 4 번 호출한다**",
    )
    args = parser.parse_args(argv)

    if not args.env_file.exists():
        print(f"환경 파일이 없습니다: {args.env_file}", file=sys.stderr)
        return 2
    load_env(args.env_file)

    # 앱 쪽 import 는 환경 파일을 **읽은 뒤에** 한다 — `Settings` 가 그때 만들어진다.
    from app.auth.crypto import KeyCipher
    from app.config import get_settings
    from app.db.session import init_engine, session_scope
    from app.errors import AppError
    from app.services import articles, daily, grouping, paragraphs, prepare

    picked = pick_date(args.pick, daily.today)

    settings = get_settings()
    draft = read_draft(args.path)

    print(f"모드 {settings.app_mode} · DB {where(settings.database_url)}")
    init_engine(settings.database_url, create_all=False)

    with session_scope() as db:
        # **묶기도 자동 경로와 같은 것을 탄다** (M13-T11). 주제 경계는 운영자 키로
        # 묻고, 키가 없거나 못 믿을 답이 오면 단어 예산으로 떨어진다 — 손으로 넣어
        # 확인한 문단이 자동 경로의 문단과 달라지면 확인한 뜻이 없다.
        try:
            texts, cut = articles.gates(draft)
        except AppError as exc:
            print(f"{exc.message} ({exc.detail})", file=sys.stderr)
            return 1

        try:
            provider = prepare.provider_for(db, KeyCipher(settings.encryption_key), settings)
        except AppError:
            provider = None
        try:
            groups = asyncio.run(
                grouping.by_topic(texts[cut.start : cut.stop], provider)
            )
        finally:
            if provider is not None:
                asyncio.run(provider.aclose())

        try:
            stored = articles.store(db, draft, picked_for=picked, groups=groups)
        except AppError as exc:
            print(f"{exc.message} ({exc.detail})", file=sys.stderr)
            return 1

        print(
            f"{'넣었다' if stored.created else '이미 있다'} "
            f"#{stored.article.id} {stored.article.title}"
        )
        print(f"문단 {stored.paragraphs} · 뉴스 날짜 {stored.article.picked_for or '(후보)'}")

        if stored.pieces != stored.paragraphs:
            print(f"토막 {stored.pieces}개를 {stored.paragraphs}문단으로 묶었다")
        for note in cut_notes(stored.skipped, stored.trimmed, paragraphs.WORD_LIMIT):
            print(note)

        if not args.prepare:
            print(f"미리 분석은 --prepare 로. 호출 {stored.paragraphs * 4}번쯤 든다")
            return 0

        cipher = KeyCipher(settings.encryption_key)
        try:
            report = asyncio.run(prepare.article(db, stored.article, cipher, settings))
        except AppError as exc:
            print(f"{exc.message} ({exc.detail})", file=sys.stderr)
            return 1

    print(
        f"새로 {report.prepared} · 재시도 {report.retried} · 건너뜀 {report.skipped}"
        f" · 일부 실패 {report.partial}"
    )
    if report.stopped_at is not None:
        print(f"{report.stopped_at}번 문단에서 멈췄다 — 네 파트가 전부 실패했다", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
