"""기사 본문 쪼개기 (M13-T3).

**입력을 꾸미지 않는다.** 아래 HTML 토막은 가디언 응답에서 그대로 떠 온 모양이다 —
직접 쓴 `<p>첫 문단</p>` 같은 입력으로는 `<aside>` 함정이 안 잡힌다. 실제로 본문에는
`<aside>` 안에 "Related:" 링크가 `<p>` 로 들어 있고, 그게 26개였다.

규칙을 왜 그렇게 정했는지는 `app/services/paragraphs.py` 머리말.
"""

from app.services.paragraphs import MIN_CHARS, clean, split

# 50자를 넘기는 평범한 문단. 길이 하한에 걸리지 않게 둔다.
LONG = (
    "The replacement crew for the International Space Station was launched "
    "late on Friday, paving the way for the return home of two astronauts."
)
LONGER = (
    "A California jury on Friday imposed a fine on the company in the case of "
    "a delivery driver burned by a scalding cup of hot tea at a store."
)


# ------------------------------------------------------- 본문이 아닌 것을 버린다


def test_a_related_link_box_is_not_a_paragraph():
    """실제 응답에서 뜬 모양. **`<aside>` 안에 `<p>` 가 있다** — 26개 있었다."""
    body = (
        '<aside> <p> <span>Related: </span>'
        '<a href="https://www.theguardian.com/world/2026/oct/15/starshield">'
        "What is Starshield, SpaceX's military-grade Starlink system?</a> </p> </aside>"
        f" <p>{LONG}</p>"
    )

    assert split(body) == [LONG]


def test_an_embedded_video_is_not_a_paragraph():
    body = (
        '<figure> <gu-atom data-atom-type="media"> <div>'
        '<iframe src="https://www.youtube-nocookie.com/embed/x"></iframe>'
        "</div> </gu-atom> <figcaption>On Thursday, the president accused the "
        "media of being unfair to the estranged mother.</figcaption> </figure>"
        f" <p>{LONG}</p>"
    )

    assert split(body) == [LONG]


def test_a_bullet_list_is_not_a_paragraph():
    body = f"<ul><li><p>{LONG}</p></li></ul><p>{LONGER}</p>"

    assert split(body) == [LONGER]


def test_a_live_blog_timestamp_is_not_a_paragraph():
    """**길이 하한이 잡는다. `<time>` 규칙을 따로 두지 않는다.**

    전에는 `<time>` 을 보고 거르는 규칙이 있었는데 깨뜨려 보니 그것 없이도 이 검사가
    통과했다 — 시각 표시는 `11.32am BST` 처럼 짧아서 하한에 먼저 걸린다. 실측으로도
    `type=liveblog` 15편의 `<time>` 문단 624개가 **전부** 50자 미만이었고,
    `type=article` 87편에는 아예 0개였다. 규칙을 다시 들이지 않는다.
    """
    body = (
        '<p class="block-time published-time">'
        '<time datetime="2026-10-21T10:32:48.177Z">11.32am '
        '<span class="timezone">BST</span></time></p>'
        f'<div class="block-elements"><p>{LONG}</p></div>'
    )

    assert split(body) == [LONG]


def test_a_quoted_passage_is_kept():
    """`<blockquote>` 는 인용된 발언이다. **버리지 않는다** — 학습 가치가 있는 산문이다."""
    body = f"<blockquote><p>{LONG}</p></blockquote>"

    assert split(body) == [LONG]


# ------------------------------------------------------------------ 길이 하한


def test_boilerplate_shorter_than_the_floor_is_dropped():
    """경계를 눈으로 보고 정한 값이다. 전부 실제로 나온 문장들이다."""
    junk = [
        "Exhibit 1:",
        "The trial continues.",
        "Reuters contributed reporting",
        "Click here if this graph does not display",  # 41자 — 40 하한은 통과한다
        "The Guardian has approached Google for comment.",
    ]
    body = "".join(f"<p>{j}</p>" for j in junk) + f"<p>{LONG}</p>"

    assert split(body) == [LONG]
    assert all(len(j) < MIN_CHARS for j in junk)


def test_a_real_short_sentence_is_kept():
    """하한이 진짜 문단까지 먹으면 안 된다. 이것도 실제로 나온 문장이다."""
    real = 'Several users mocked the Falcons as the "Bird Reich" on social media.'
    assert len(real) >= MIN_CHARS

    assert split(f"<p>{real}</p>") == [real]


# ------------------------------------------------------------------ 글자 다루기


def test_inline_markup_is_stripped_but_the_words_stay():
    body = (
        "<p>The <strong>Met Office</strong> found that the "
        '<a href="/x">climate crisis</a> made this <em>extreme</em> heat '
        "about 130 times more likely than before.</p>"
    )

    assert split(body) == [
        (
            "The Met Office found that the climate crisis made this extreme heat "
            "about 130 times more likely than before."
        )
    ]


def test_entities_become_characters():
    assert clean("Trump &amp; Musk said &ldquo;no&rdquo;") == "Trump & Musk said “no”"


def test_entities_are_unescaped_after_tags_are_stripped():
    """순서가 거꾸로면 `&lt;p&gt;` 가 태그로 보여 글자가 사라진다."""
    assert clean("the tag &lt;p&gt; means paragraph") == "the tag <p> means paragraph"


def test_a_line_break_becomes_a_space_not_nothing():
    """지우면 앞뒤 단어가 붙는다."""
    assert clean("first line<br>second line") == "first line second line"
    assert clean("first<br/>second") == "first second"


def test_whitespace_is_collapsed():
    assert clean("  a \n\n  b\t c  ") == "a b c"


# ------------------------------------------------------------------ 모양새


def test_the_order_is_kept():
    body = f"<p>{LONG}</p><p>{LONGER}</p>"

    assert split(body) == [LONG, LONGER]


def test_an_empty_body_gives_nothing():
    assert split("") == []
    assert split("   ") == []


def test_a_body_with_no_paragraph_gives_nothing():
    assert split("<h2>Just a subheading</h2>") == []


def test_attributes_on_the_paragraph_tag_do_not_matter():
    body = f'<p class="block-element" data-x="1">{LONG}</p>'

    assert split(body) == [LONG]
