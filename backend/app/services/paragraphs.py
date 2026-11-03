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
경로의 제한(local 2000 · cloud 1200)은 여기 적용되지 않는다 — 미리 분석은 서버가
돌리므로 그 경로를 타지 않는다. 적용된다 쳐도 **cloud 상한(1200자)을 넘는 문단은
0개**다 — 잰 최댓값이 1,021자였다. (상한이 800자이던 때는 5개였다.)

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

### 쪼개는 것과 **얼마나 쓸 것인가**는 다른 규칙이다

위의 모든 규칙은 "무엇이 문단인가" 를 가린다. 그 문단들 중 **몇 개까지 쓸 수 있는가**
는 출처 약관이 정하고, 그건 `excerpt()` 가 든다 (`M13-T9`). 둘을 나눠 둔 이유는
고르는 쪽(`M13-T4`)이 **앉히기 전에** 후보를 재야 하기 때문이다 — 쓸 수 있는 토막이
안 나오는 기사는 넣지 않고 다음 후보로 넘어간다.

[문서] plan/DONE.md M13-T11
[문서] plan/DONE.md M13-T3
[문서] plan/DONE.md M13-T9
"""

import html
import re
from dataclasses import dataclass

# 50자 미만은 길어도 한 문장이라 네 파트가 쓸 것이 없다. 근거는 머리말.
MIN_CHARS = 50

# **출처 약관이 허용하는 인용 분량.** 공백으로 가른 낱말로 센다 (가디언, 2026-11-03).
#
# **설정값으로 두지 않는다.** 운영자가 올릴 수 있는 손잡이로 만들면 약관을 넘기는
# 길을 하나 두는 셈이다. 출처가 둘이 되는 날 출처별 값으로 옮긴다 (`M13-T7`).
WORD_LIMIT = 500

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


@dataclass(frozen=True)
class Excerpt:
    """쓸 수 있는 문단 구간. **이어진 한 토막이다.**

    끊어 쓰지 않는 이유는 산문이기 때문이다 — 상한을 넘긴 문단만 빼고 뒤를 이어
    붙이면 대명사가 가리킬 것을 잃고 "그러나" 가 앞 문장 없이 시작한다.

    `stop` 은 **끝 다음**이다(파이썬 슬라이스와 같게). 빈 구간은 거짓이므로
    `if not cut:` 으로 "쓸 수 없는 기사" 를 가린다.
    """

    start: int
    stop: int
    words: int

    def __bool__(self) -> bool:
        return self.stop > self.start


def words(text: str) -> int:
    """낱말 수. **공백으로 가른다** — 약관이 세는 방식이 그것이다."""
    return len(text.split())


def excerpt(texts: list[str]) -> Excerpt:
    """쓸 수 있는 문단 구간을 고른다. 없으면 빈 구간 (M13-T9).

    ```
    1. 앞에서부터 누적이 상한을 넘지 않는 문단까지
    2. 첫 문단 하나가 이미 상한을 넘으면 그것을 버리고 다음 문단을 시작점으로
    3. 모든 문단이 상한을 넘으면 빈 구간 — 고르는 쪽이 다음 후보로 넘어간다
    ```

    **2번은 시작점을 찾는 규칙이지 건너뛰는 규칙이 아니다.** 시작점을 정한 뒤에는
    1번이 그대로 돌아 거기서부터 이어진 토막을 낸다.

    3번은 **닿지 않는 가지로 보인다** — `M13-T1` 의 실측에서 문단 최댓값이
    1,021자(≈170단어)였다. 그래도 검사를 단다. 안 달면 나중에 "왜 이 분기에
    검사가 없지" 가 되고, 출처가 바뀌면 그때 진짜로 닿는다.
    """
    for start in range(len(texts)):
        if words(texts[start]) > WORD_LIMIT:
            continue  # 이 문단 하나가 벌써 상한을 넘는다 — 시작점이 될 수 없다
        total = 0
        stop = start
        for text in texts[start:]:
            count = words(text)
            if total + count > WORD_LIMIT:
                break
            total += count
            stop += 1
        return Excerpt(start=start, stop=stop, words=total)
    return Excerpt(start=0, stop=0, words=0)


#: 한 묶음에 담을 낱말 수. **호출 수와 입력 상한 사이에서 고른 값이다** (M13-T11).
#:
#: 실측(기사 13편)에서 120단어는 기사당 호출을 49 → 21 로 줄이고(58%) 묶인 글이
#: 최대 761자였다. 150은 68% 절약이지만 975자이고, 200은 1,249자로 **cloud 입력
#: 상한(1200자)을 넘는다** — 넘으면 회원 경로의 제한과 같은 벽에 부딪힌다.
GROUP_WORDS = 120


def group(texts: list[str], *, budget: int = GROUP_WORDS) -> list[list[int]]:
    """문단들을 단어 예산까지 이어 붙일 **묶음**으로 가른다. 각 묶음은 자리 번호 목록.

    **글이 아니라 번호를 돌려준다.** 번호를 돌려주면 부르는 쪽이 원문에서 직접
    이어 붙이므로 **본문이 한 글자도 바뀌지 않는다.** LLM 이 경계를 고르는 길
    (`services/grouping.py`)과 **같은 모양**이어서, 그쪽이 실패하면 이것으로
    그대로 떨어질 수 있다.

    한 문단이 혼자 예산을 넘으면 **쪼개지 않고** 그대로 한 묶음이 된다 —
    쪼개면 문장이 끊긴다. 실측 최댓값이 1,021자라 입력 상한 안이다.
    """
    out: list[list[int]] = []
    current: list[int] = []
    total = 0
    for index, text in enumerate(texts):
        count = words(text)
        if current and total + count > budget:
            out.append(current)
            current, total = [], 0
        current.append(index)
        total += count
    if current:
        out.append(current)
    return out


def joined(texts: list[str], groups: list[list[int]], *, more: bool = False) -> list[str]:
    """묶음 번호를 **원문에서** 이어 붙인다. 본문은 바뀌지 않는다.

    `more` 가 참이면 마지막 묶음 끝에 `…` 를 붙인다 — **뒤에 안 쓴 문단이 있다는
    뜻이다** (분량 상한에 걸려 버린 것). 추측이 아니라 `excerpt()` 가 알려 준 사실이다.
    끝이 잘렸다는 표시 없이 내보내면 읽는 쪽이 기사가 거기서 끝난 줄 안다.
    """
    out = [" ".join(texts[i] for i in g) for g in groups]
    if more and out:
        # **공백 없이 붙인다.** 띄우면 `words()` 가 낱말 하나로 세고, 상한에 딱 걸린
        # 기사를 다시 앉힐 때 `excerpt()` 가 501낱말로 읽어 **문단을 지운다**
        # (그 분석까지 사라진다). 검사가 451 vs 450 으로 그걸 잡았다.
        out[-1] = f"{out[-1]}…"
    return out
