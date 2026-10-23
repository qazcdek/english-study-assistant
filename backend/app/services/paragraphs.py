"""기사 본문(HTML)을 분석 단위로 쪼갠다.

**순수 함수다.** HTTP 도 DB 도 타지 않는다 — 출처가 늘어도 이 모듈은 그대로다.

### 실측으로 정한 규칙 (2026-10-23, 가디언 104편 · 문단 1,442개)

본문에 `<p>` 만 들어 있을 거라 짐작하면 틀린다. 실제로 나온 태그는 이렇다.

```
<p> 642   <a> 193   <strong> 144   <div> 83   <time> 70   <span> 67
<h2> 29   <aside> 26   <li> 11   <blockquote> 9   <figure> 2   <iframe> 2
```

**`<aside>` 안에 `<p>` 가 26개 있었다.** "Related: <기사 링크>" 꼴의 추천 블록이라
그대로 긁으면 가짜 문단이 섞인다. 일반 기사에도 1~3개씩 들어 있다.

`<blockquote>` 는 **버리지 않는다.** 인용된 발언이라 학습 가치가 있는 산문이다.
`<h2>` 는 소제목인데 `<p>` 가 아니라서 저절로 빠진다.

### 왜 50자인가

경계를 **전부 눈으로 보고** 정했다. 길이만으로는 못 가른다 —
`"Click here if this graph does not display"` 가 **41자**라서 40 하한을 통과한다.

```
10~47자   Exhibit 1: / The trial continues. / Verdict: the real thing
          Reuters contributed reporting / Click here if this graph does not display
          The Guardian has approached Google for comment.
52자부터  Several users mocked the Falcons as the "Bird Reich".
```

50자 미만은 **길어도 한 문장**이라 네 파트(번역·표현·구조·총평)가 쓸 것이 없다.
1,442개 중 24개(1.7%)가 걸러진다.

**내용으로 가려야 하는 것은 안 잡힌다** — 위 `Click here…` 처럼 50자를 넘는
상용구는 통과한다. 금칙어 목록을 만들지 않은 이유는 그쪽이 조용히 썩기 때문이다.
가디언이 문구를 바꾸면 목록은 아무 말 없이 무력해진다.

### 길이 제한에 걸리지 않는다

문단 1,442개 중 **2000자를 넘는 것이 0개**였다(최대 1,021자). 회원이 직접 치는
경로의 제한(local 2000 · cloud 800)은 여기 적용되지 않는다 — 미리 분석은 서버가
돌리므로 그 경로를 타지 않는다. 다만 **800자를 넘는 문단은 5개 있었다.**

### 라이브블로그는 여기서 거르지 않는다

쪼개기가 아니라 **고르기**의 일이다(`M13-T4`). 가디언이 `type` 으로 구별해 준다 —
`article` / `liveblog`. 라이브블로그를 섞으면 50자 미만 쓰레기가 2% → 11% 로
늘고 "Hm." · "Finally!" 같은 것이 문단이 된다.

**`<time>` 을 따로 거르지 않는다.** 처음에는 라이브블로그의 시각 표시(`11.32am BST`)를
잡으려고 규칙을 하나 더 뒀는데, **깨뜨려 보니 그 규칙 없이도 검사가 통과했다.**
재 보니 이유가 분명했다 — `type=article` 87편에는 `<time>` 을 든 `<p>` 가 **0개**이고,
`type=liveblog` 15편에는 **624개인데 전부 50자 미만**이다. 길이 하한이 하나도
안 빼놓고 다 잡으므로 그 규칙이 단독으로 잡는 경우는 **102편에서 0개**였다.
추측으로 둔 한 겹이었고, 지웠다.

[문서] plan/DONE.md M13-T3
"""

import html
import re

# 50자 미만은 길어도 한 문장이라 네 파트가 쓸 것이 없다. 근거는 머리말.
MIN_CHARS = 50

# **통째로 버리는 블록.** 안에 `<p>` 가 있어도 본문이 아니다.
# `gu-atom` 은 가디언이 임베드에 쓰는 자체 태그다.
DROP_BLOCKS = ("aside", "figure", "gu-atom", "iframe", "ul", "ol")

_BLOCK_RE = re.compile(
    r"<(" + "|".join(DROP_BLOCKS) + r")\b.*?</\1\s*>", re.DOTALL | re.IGNORECASE
)
_PARA_RE = re.compile(r"<p\b[^>]*>(.*?)</p\s*>", re.DOTALL | re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def split(body: str) -> list[str]:
    """본문 HTML 에서 분석할 문단만 순서대로 꺼낸다."""
    body = _BLOCK_RE.sub(" ", body or "")
    return [
        text
        for raw in _PARA_RE.findall(body)
        if len(text := clean(raw)) >= MIN_CHARS
    ]


def clean(raw: str) -> str:
    """한 문단의 안쪽 태그를 걷고 공백을 고른다.

    `<br>` 을 **공백으로** 바꾼다 — 지우면 앞뒤 단어가 붙는다.
    태그를 걷은 **뒤에** 엔티티를 푼다. 먼저 풀면 `&lt;p&gt;` 가 태그로 보인다.
    """
    text = _BR_RE.sub(" ", raw)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()
