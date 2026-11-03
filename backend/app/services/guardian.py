"""가디언에서 후보 기사를 가져온다 (M13-T4).

**가져오기만 한다.** 고르는 것은 `daily.py`, 앉히는 것은 `articles.store` 다.
여기서 하는 일은 HTTP 하나와 응답을 `Draft` 로 옮기는 것뿐이다 — 그래서 출처가
늘어도 이 모듈을 흉내 낸 파일이 하나 더 생기면 끝난다.

### 섹션 단위로만 가져온다

`show-most-viewed=true` 가 **섹션에서만 돈다** (`M13-T1` 실측 — `/` 는 0건,
`/search` 는 필드 자체가 없다). 그래서 섹션을 하나 골라야 하고, 지금은 `world`
하나다. 분야를 여러 개로 넓히는 것은 `M15` 가 한다.

### 라이브블로그는 여기서 버린다

`type` 이 `article` 이 아닌 것을 안 내려준다. 쪼개기(`paragraphs.py`)가
"라이브블로그는 여기서 거르지 않는다 — 쪼개기가 아니라 **고르기**의 일이다" 라고
적어 둔 그 자리다. 섞으면 50자 미만 쓰레기가 2% → 11% 로 늘고 "Hm." 같은 것이
문단이 된다. 실측에서도 인기 1위가 라이브블로그인 날이 있었다(106문단 · 3,368단어).

### 순위를 다시 매기지 않는다

가디언이 준 순서가 곧 인기 순위다. **숫자 없는 완전 순서**라 1위가 언제나 유일하게
정해지므로(`M13-T1`) "동률이면 최신" 규칙은 닿지 않는다 — 그 판단도 거기 적혀 있다.

[문서] plan/DONE.md M13-T4
"""

from datetime import datetime

import httpx

from app.config import Settings
from app.errors import ArticleSourceError
from app.services.articles import Draft

#: 인기 목록을 가져올 섹션. **하나뿐인 이유는 머리말** (`M15` 가 넓힌다).
SECTION = "world"

#: 한 번에 볼 후보 수. 실측에서 `world` 가 13~20건을 줬으므로 넉넉하다.
PAGE_SIZE = 20

#: 받을 필드. `body` 가 없으면 쪼갤 것이 없고, `byline` 이 없으면 앉힐 수 없다
#: (`M13-T10` — 약관이 크레딧을 요구한다).
FIELDS = "body,byline,wordcount"


async def candidates(
    settings: Settings, *, section: str = SECTION, client: httpx.AsyncClient | None = None
) -> list[Draft]:
    """인기 순서대로 후보 `Draft` 목록. **기사만** 담긴다.

    `ArticleSourceError` 는 출처가 대답하지 않았다는 뜻이다 — 고르는 쪽이 이것을
    보고 쿨다운을 적는다. 후보가 **0개인 것도** 오류로 본다: 응답은 왔지만 쓸 것이
    없으면 뉴스를 만들 수 없고, 조용히 성공으로 두면 왜 뉴스가 없는지 아무도 모른다.
    """
    if not settings.guardian_api_key:
        raise ArticleSourceError(detail="GUARDIAN_API_KEY 가 비어 있습니다")

    params = {
        "show-most-viewed": "true",
        "show-fields": FIELDS,
        "page-size": str(PAGE_SIZE),
        "api-key": settings.guardian_api_key,
    }
    url = f"{settings.guardian_base_url}/{section}"
    owned = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(settings.guardian_timeout))
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError as exc:
        # **키를 메시지에 담지 않는다.** `httpx` 의 오류 문구에는 요청 URL 이 들어가고
        # 거기에 `api-key` 가 붙어 있다 — 그대로 쿨다운 표의 `reason` 에 적히면
        # DB 와 화면에 키가 남는다.
        raise ArticleSourceError(detail=f"{type(exc).__name__}") from exc
    except ValueError as exc:
        raise ArticleSourceError(detail="응답이 JSON 이 아니다") from exc
    finally:
        if owned:
            await client.aclose()

    rows = (body.get("response") or {}).get("mostViewed") or []
    drafts = [draft for row in rows if (draft := _draft(row)) is not None]
    if not drafts:
        raise ArticleSourceError(detail=f"{section} 인기 목록에 쓸 기사가 없다")
    return drafts


def _draft(row: dict) -> Draft | None:
    """응답 한 줄을 `Draft` 로. 기사가 아니거나 칸이 비면 `None`.

    **여기서 거르는 것은 "모양이 안 맞는 것" 까지다.** 분량(`M13-T9`)과 크레딧
    (`M13-T10`)은 `store()` 가 보고 거부하므로 두 번 적지 않는다 — 손으로 넣는
    길과 자동 경로가 **같은 관문**을 지나야 손으로 확인한 것을 믿을 수 있다.
    """
    if row.get("type") != "article":
        return None
    fields = row.get("fields") or {}
    try:
        published_at = datetime.fromisoformat(row["webPublicationDate"])
    except (KeyError, ValueError):
        return None
    if not all(row.get(key) for key in ("id", "webUrl", "webTitle")):
        return None
    return Draft(
        source="guardian",
        source_id=row["id"],
        url=row["webUrl"],
        title=row["webTitle"],
        byline=(fields.get("byline") or "").strip(),
        section=row.get("sectionId") or "",
        published_at=published_at,
        body=fields.get("body") or "",
    )
