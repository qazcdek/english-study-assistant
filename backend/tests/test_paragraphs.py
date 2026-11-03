"""기사 본문 쪼개기 (M13-T3).

**입력을 꾸미지 않는다.** 아래 HTML 토막은 가디언 응답에서 그대로 떠 온 모양이다 —
직접 쓴 `<p>첫 문단</p>` 같은 입력으로는 `<aside>` 함정이 안 잡힌다. 실제로 본문에는
`<aside>` 안에 "Related:" 링크가 `<p>` 로 들어 있고, 그게 26개였다.

규칙을 왜 그렇게 정했는지는 `app/services/paragraphs.py` 머리말.
"""

from app.services.paragraphs import MIN_CHARS, WORD_LIMIT, clean, excerpt, split, words

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


# ------------------------------------------- 약관이 허용하는 분량만 쓴다 (M13-T9)


def para(count: int, mark: str = "w") -> str:
    """`count` 낱말짜리 문단 하나. **공백으로 가른 수**가 그대로 `count` 다."""
    return " ".join([mark] * count)


def test_a_short_article_is_taken_whole():
    """상한 안에 다 들면 **아무것도 자르지 않는다.**"""
    cut = excerpt([para(100), para(100), para(100)])

    assert (cut.start, cut.stop, cut.words) == (0, 3, 300)
    assert bool(cut) is True


def test_accumulation_stops_before_the_paragraph_that_crosses_the_limit():
    """**누적**으로 센다. 넘기는 문단은 넣지 않는다 — 넣고 나서 줄이지 않는다."""
    cut = excerpt([para(300), para(150), para(100), para(10)])

    # 300+150=450 까지. 셋째를 넣으면 550 이라 거기서 멈춘다.
    assert (cut.start, cut.stop, cut.words) == (0, 2, 450)


def test_a_paragraph_landing_exactly_on_the_limit_is_taken():
    """경계는 **이내**다. 500 은 넘은 것이 아니다."""
    cut = excerpt([para(400), para(100), para(1)])

    assert (cut.start, cut.stop, cut.words) == (0, 2, 500)


def test_crossing_at_the_second_paragraph_leaves_only_the_first():
    """사용자가 든 예 그대로 — 2번째까지 넘으면 1번째까지."""
    cut = excerpt([para(400), para(200)])

    assert (cut.start, cut.stop) == (0, 1)


def test_an_oversized_first_paragraph_moves_the_start_instead_of_failing():
    """첫 문단 하나가 벌써 상한을 넘으면 **그것을 버리고 다음을 시작점으로.**"""
    cut = excerpt([para(WORD_LIMIT + 1), para(80), para(90)])

    assert (cut.start, cut.stop, cut.words) == (1, 3, 170)


def test_the_start_search_walks_past_every_oversized_paragraph():
    """시작점을 찾을 때까지 **계속** 넘긴다 — 한 번만 넘기고 포기하지 않는다."""
    cut = excerpt([para(600), para(700), para(80)])

    assert (cut.start, cut.stop) == (2, 3)


def test_the_excerpt_is_one_unbroken_run():
    """**중간을 건너뛰지 않는다.** 상한을 넘긴 문단 뒤의 짧은 문단을 당겨오면
    산문이 끊기고 대명사가 가리킬 것을 잃는다. 시작점을 찾는 규칙은 *앞*에만 돈다."""
    cut = excerpt([para(80), para(600), para(80)])

    # 2번(600단어)에서 멈춘다. 3번을 당겨와 (0,1)+(2,3) 으로 만들지 않는다.
    assert (cut.start, cut.stop, cut.words) == (0, 1, 80)


def test_an_article_whose_every_paragraph_is_oversized_is_unusable():
    """**닿지 않는 가지로 보이지만 검사를 단다** — 근거는 `paragraphs.py` 머리말.
    고르는 쪽(`M13-T4`)이 이걸 보고 다음 인기 기사로 넘어간다."""
    cut = excerpt([para(600), para(700)])

    assert bool(cut) is False
    assert (cut.start, cut.stop, cut.words) == (0, 0, 0)


def test_no_paragraphs_at_all_is_also_unusable():
    """`split()` 이 빈 목록을 낼 수 있다 — 사진 기사가 그렇다."""
    assert bool(excerpt([])) is False


def test_words_are_counted_by_whitespace_because_that_is_what_the_terms_count():
    """약관이 세는 방식이다. 문장부호나 하이픈으로 가르지 않는다."""
    assert words("state-of-the-art naval vessels") == 3
    assert words("Hello,  world!") == 2
    assert words("  ") == 0


def test_the_real_article_is_cut_where_it_was_measured():
    """개발 DB 의 기사 #1 을 **실제로 재서** 나온 숫자다 (M13-T9 의 ONGOING).
    16문단 688단어 → **1~11문단 455단어.** 12번(60단어)이 515가 되어 탈락한다."""
    measured = [35, 41, 23, 48, 24, 51, 45, 47, 56, 52, 33, 60, 32, 29, 50, 62]
    assert sum(measured) == 688

    cut = excerpt([para(n) for n in measured])

    assert (cut.start, cut.stop, cut.words) == (0, 11, 455)
