"""주소 검사 — 코드와 문서가 서로를 가리키는 포인터가 실제로 맞는지 본다.

도달성(test_docs_graph.py)은 문서끼리의 길만 본다. 그런데 이 저장소에서 가장 조용히
썩는 포인터는 **코드 주석이 들고 있는 문서 주소**다. 문서 번호는 뜻이 아니라 주소라서
(11 3.3) 절 번호 하나만 밀려도 주석이 엉뚱한 곳을 가리키는데, 사람도 기계도 모른다.

전부 규칙 기반이라 파일을 읽는 것 말고는 하는 일이 없다 — 앱을 띄우지 않는다.
"""

from __future__ import annotations

import re

from tests import docmap
from tests.docmap import (
    ROOT,
    ROOT_DOC,
    all_docs,
    code_refs,
    doc_refs,
    header_of,
    outside_fences,
    rel,
    section_body,
    sections_of,
)


def standard_docs():
    """머리말 규약(00 §4.1)이 걸리는 문서. README 는 저장소의 얼굴이고 CLAUDE.md 는
    꼭대기라 둘 다 머리말을 달지 않는다."""
    return sorted(d for d in all_docs() if d.parts[-2] in ("documents", "plan"))

# 상태 어휘는 셋뿐이다 (CLAUDE.md 3절).
STATES = {"유효", "기록", "대체됨"}
# 어디로 들어와도 머리말에 다 있어야 한다 (11 2.2). 옆길은 `함께` 또는 색인의 `아래`.
REQUIRED = ("층", "상태", "읽어야 할 때", "위")


def test_every_document_carries_the_standard_header():
    missing = []
    for doc in standard_docs():
        header = header_of(doc)
        gaps = [k for k in REQUIRED if k not in header]
        if not ({"함께", "아래"} & set(header)):
            gaps.append("함께")
        if gaps:
            missing.append(f"{rel(doc)} — {' · '.join(gaps)}")
    assert not missing, "머리말에 빠진 칸:\n  " + "\n  ".join(missing)


def test_document_states_use_the_three_declared_words():
    wrong = [
        f"{rel(doc)} — '{header_of(doc).get('상태')}'"
        for doc in standard_docs()
        if header_of(doc).get("상태") not in STATES
    ]
    assert not wrong, (
        "상태 어휘는 " + " · ".join(sorted(STATES)) + " 셋뿐이다:\n  " + "\n  ".join(wrong)
    )


def test_code_writes_document_addresses_in_the_one_agreed_form():
    bad = [f"{r.where()}  {r.doc} — {r.problem}" for r in code_refs() if r.problem]
    assert not bad, "주소 표기 규약(10 7절) 위반:\n  " + "\n  ".join(bad)


def test_every_document_address_in_the_code_resolves():
    names = {p.name for p in all_docs()}
    dangling = []
    for ref in code_refs():
        if ref.doc not in names:
            dangling.append(f"{ref.where()}  없는 문서 {ref.doc}")
        elif ref.section and ref.section not in sections_of(ROOT / "documents" / ref.doc):
            dangling.append(f"{ref.where()}  {ref.doc} 에 §{ref.section} 절이 없다")
    assert not dangling, "코드가 가리키는 문서 주소가 썩었다:\n  " + "\n  ".join(dangling)


def test_the_doc_to_doc_scan_actually_found_something():
    """빈 목록을 훑으면 아래 둘이 통과만 한다. 찾았다는 것부터 확인한다."""
    sectioned = [r for r in doc_refs() if r.section]
    assert len(sectioned) >= 20, f"문서→문서 절 주소를 {len(sectioned)}개만 찾았다"


def test_every_document_address_in_a_document_resolves():
    """문서가 가리키는 절도 실제로 있어야 한다.

    전에는 **코드→문서만** 봤다. 그래서 09 와 14 가 가리키는 07 §6.5 의 번호를 바꿔도
    "이상 없음" 이 나왔다 — 실제로 깨뜨려 확인했다 (M11-T2).
    """
    names = {p.name for p in all_docs()}
    dangling = []
    for ref in doc_refs():
        if ref.section is None:
            continue  # 그래프 검사가 본다
        if ref.doc not in names:
            dangling.append(f"{ref.where()}  없는 문서 {ref.doc}")
        elif ref.section not in sections_of(ROOT / "documents" / ref.doc):
            dangling.append(f"{ref.where()}  {ref.doc} 에 §{ref.section} 절이 없다")
    assert not dangling, "문서가 가리키는 절 주소가 썩었다:\n  " + "\n  ".join(dangling)


def test_a_referenced_section_is_not_empty():
    """가리켜지는 절은 내용을 들고 있어야 한다.

    **내용을 다른 문서로 옮기고 제목만 남기는 것**이 가장 잡기 어려운 어긋남이다.
    주소는 멀쩡히 해석되는데 가리키는 내용이 없다. 옮긴 자리에 **길잡이 한 줄**을
    남겼다면 통과한다 — 그게 지키려는 규약이다 (11 §3.6).
    """
    hollow = []
    sectioned = [r for r in doc_refs() + code_refs() if r.section and not r.problem]
    for ref in sectioned:
        doc = ROOT / "documents" / ref.doc
        if not doc.is_file() or ref.section not in sections_of(doc):
            continue  # 위 두 검사가 본다
        if len(section_body(doc, ref.section)) < 40:
            hollow.append(f"{ref.where()} 가 가리키는 {ref.doc} §{ref.section} 이 비었다")
    assert not hollow, (
        "옮기고 길잡이를 안 남겼다:\n  " + "\n  ".join(sorted(set(hollow))) + "\n(11 §3.6)"
    )


def test_enforcement_pointers_point_both_ways():
    """문서가 '이 테스트가 나를 강제한다' 고 적었으면, 그 테스트도 문서를 알아야 한다."""
    broken = []
    for doc in sorted(all_docs()):
        for path in re.findall(r"[\w./-]+\.py", header_of(doc).get("강제", "")):
            test_file = ROOT / path
            if not test_file.is_file():
                broken.append(f"{rel(doc)} 의 강제 `{path}` 가 없는 파일이다")
            elif doc.name not in test_file.read_text(encoding="utf-8"):
                broken.append(f"{path} 가 {doc.name} 를 가리키지 않는다 (한쪽만 안다)")
    assert not broken, "강제 포인터가 짝이 안 맞는다:\n  " + "\n  ".join(broken)


def test_documents_cited_by_code_are_listed_in_the_claude_md_table():
    """코드가 근거로 드는 문서라면, 그 코드를 고치는 사람에게 펴라고 말해 줘야 한다."""
    table = ROOT_DOC.read_text(encoding="utf-8").split("## 4.")[1].split("## 5.")[0]
    listed = set(docmap._DOC_NAME.findall(table))
    cited = {ref.doc for ref in code_refs() if ref.src.parts[-2] != "tests"}
    assert not cited - listed, (
        "코드가 가리키는데 CLAUDE.md 4절 표에 없는 문서: " + " · ".join(sorted(cited - listed))
    )


def test_every_command_in_the_tooling_doc_is_wired_into_dev_sh():
    """12-tooling.md 7절의 명령이 `dev.sh` 의 분기와 help 목록에 다 있어야 한다.

    `ptr` 를 case 에만 넣고 머리 주석을 안 고쳐 한 마일스톤 동안 help 에 없었다.
    """
    table = (ROOT / "documents" / "12-tooling.md").read_text(encoding="utf-8").split("## 7.")[1]
    verbs = set(re.findall(r"`\./dev\.sh ([a-z]+)`", table))
    assert verbs, "7절에서 명령을 하나도 못 찾았다. 표 형식이 바뀌었다"

    dev = (ROOT / "dev.sh").read_text(encoding="utf-8")
    branches = {
        verb
        for label in re.findall(r"^ {4}([a-z|-]+)\)$", dev, re.MULTILINE)
        for verb in label.split("|")
    }
    helped = set(re.findall(r"^# +\./dev\.sh ([a-z]+)", dev, re.MULTILINE))

    gaps = []
    for verb in sorted(verbs):
        missing = [w for w, s in (("분기", branches), ("help 목록", helped)) if verb not in s]
        if missing:
            gaps.append(f"{verb} — {' · '.join(missing)} 에 없다")
    assert not gaps, "dev.sh 에 안 걸린 명령:\n  " + "\n  ".join(gaps)


# ----------------------------------------------- DONE 의 구조 (union 머지 뒤처리)
#
# DONE 은 맨 위에 덧붙이기만 하는 파일이라 두 브랜치가 같은 자리를 건드린다.
# 내용이 다투는 것이 아니라 **자리만 겹치는** 것이므로 `.gitattributes` 가
# `merge=union` 으로 양쪽을 다 남긴다. 대신 날짜 머리글이 두 번 남을 수 있다 —
# 그 뒤처리를 여기서 잡는다 (H-024).

_DATE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s*$")
_ENTRY = re.compile(r"^### (M\d+-T\d+|H-\d+) ·")


def _done_outline() -> list[tuple[int, str, str]]:
    """(줄 번호, 'date' | 'entry', 값). 울타리 안의 서식 예시는 건너뛴다."""
    done = ROOT / "documents" / "plan" / "DONE.md"
    outline = []
    for n, line in outside_fences(done.read_text(encoding="utf-8")):
        if m := _DATE.match(line):
            outline.append((n, "date", m.group(1)))
        elif m := _ENTRY.match(line):
            outline.append((n, "entry", m.group(1)))
    return outline


def test_the_done_outline_was_actually_found():
    """빈 목록을 훑으면 아래 검사들이 통과만 한다."""
    outline = _done_outline()

    assert sum(1 for _, kind, _ in outline if kind == "date") >= 3
    assert sum(1 for _, kind, _ in outline if kind == "entry") >= 10


def test_done_has_no_duplicate_date_heading():
    """union 머지가 같은 날짜 머리글을 두 번 남길 수 있다. 그때 한쪽으로 모은다."""
    dates = [value for _, kind, value in _done_outline() if kind == "date"]

    doubled = sorted({d for d in dates if dates.count(d) > 1})
    assert not doubled, f"날짜 머리글이 두 번 나온다: {doubled}"


def test_done_date_headings_are_in_descending_order():
    """날짜 역순으로 읽는 문서다."""
    dates = [value for _, kind, value in _done_outline() if kind == "date"]

    assert dates == sorted(dates, reverse=True), f"날짜 머리글 순서가 어긋났다: {dates}"


def test_every_entry_sits_under_its_own_date():
    """항목이 들고 있는 날짜와 머리글이 같아야 한다.

    **순서 검사로는 안 잡힌다.** 실제로 2026-10-22 절을 끼워 넣다가 **2026-10-21
    머리글을 먹어서** H-021 이하 전부가 22일 밑에 들어가 있었는데, 남은 머리글은
    여전히 내림차순이라 아무것도 깨지지 않았다. 일부러 머리글을 지워 보고 알았다.
    """
    done = (ROOT / "documents" / "plan" / "DONE.md").read_text(encoding="utf-8")
    lines = dict(outside_fences(done))

    wrong, heading = [], None
    for line, kind, value in _done_outline():
        if kind == "date":
            heading = value
            continue
        own = next(
            (
                m.group(1)
                for n in range(line + 1, line + 4)
                if (m := re.match(r"^(\d{4}-\d{2}-\d{2})", lines.get(n, "")))
            ),
            None,
        )
        if own is None:
            wrong.append(f"DONE.md:{line}  {value} 에 날짜 줄이 없다")
        elif own != heading:
            wrong.append(f"DONE.md:{line}  {value} 는 {own} 인데 머리글은 {heading}")
    assert not wrong, "항목과 날짜 머리글이 어긋났다:\n  " + "\n  ".join(wrong)


def test_no_tag_has_two_entries_in_done():
    """태그 번호는 재사용하지 않는다(CLAUDE.md 5절 5항). 두 번 나오면 union 의 흔적이다."""
    tags = [value for _, kind, value in _done_outline() if kind == "entry"]

    doubled = sorted({t for t in tags if tags.count(t) > 1})
    assert not doubled, f"DONE 에 같은 태그가 두 번 있다: {doubled}"


def test_every_done_entry_sits_under_a_date_heading():
    """날짜 머리글 위에 끼워 넣으면 그 항목은 어느 날의 것도 아니게 된다."""
    orphans = [
        f"DONE.md:{line}  {value}"
        for line, kind, value in _done_outline()
        if kind == "entry" and not _seen_date_before(line)
    ]
    assert not orphans, "날짜 머리글 밖에 있는 항목:\n  " + "\n  ".join(orphans)


def _seen_date_before(line: int) -> bool:
    return any(n < line and kind == "date" for n, kind, _ in _done_outline())


# ------------------------------------- 세부의 자리 (ONGOING ↔ DONE ↔ 체크박스)
#
# 세부를 둘 자리가 DONE 뿐이었고, DONE 은 끝난 뒤에 쓰는 문서다. 그래서 진행 중인
# 세부가 한 줄 요약에 밀려 들어갔고, **짧은 줄은 틀려도 맞아 보인다** (H-027).
# 이제 자리가 상태에 따라 갈리므로, 그 짝이 맞는지는 글자 비교로는 부족하다.

PLAN = ROOT / "documents" / "plan"
_TRACKED = re.compile(r"^- \[(.)\]\s+(M\d+-T\d+|H-\d+)\b")


def _tracked() -> dict[str, str]:
    """ROADMAP · ISSUES 의 모든 태그 → 체크박스 글자."""
    states = {}
    for name in ("ROADMAP.md", "ISSUES.md"):
        for _, line in outside_fences((PLAN / name).read_text(encoding="utf-8")):
            if m := _TRACKED.match(line):
                states[m.group(2)] = m.group(1)
    return states


def _sections(name: str) -> set[str]:
    """그 문서가 세부를 들고 있는 태그들."""
    pattern = re.compile(r"^### (M\d+-T\d+|H-\d+) ·")
    return {
        m.group(1)
        for _, line in outside_fences((PLAN / name).read_text(encoding="utf-8"))
        if (m := pattern.match(line))
    }


def test_the_tracking_docs_were_actually_read():
    """빈 목록을 훑으면 아래 검사들이 통과만 한다."""
    assert len(_tracked()) >= 20
    assert len(_sections("DONE.md")) >= 10


def test_every_ongoing_section_has_a_tracked_tag():
    """ONGOING 에만 있는 태그는 추적되지 않는다 — 아무도 그 일이 열린 줄 모른다."""
    orphans = sorted(_sections("ONGOING.md") - set(_tracked()))

    assert not orphans, f"ROADMAP · ISSUES 에 없는 태그가 ONGOING 에 있다: {orphans}"


def test_everything_in_ongoing_is_open():
    """끝난 일이 ONGOING 에 남아 있으면, 다음에 고를 때 이미 한 일을 다시 집는다."""
    states = _tracked()
    closed = sorted(tag for tag in _sections("ONGOING.md") if states.get(tag) != "~")

    assert not closed, f"`[~]` 가 아닌데 ONGOING 에 있다: {closed}"


def test_no_tag_has_detail_in_both_places():
    """**옮겼으면 지운다.** 한 태그의 세부가 두 곳에 있으면 갈라지고, 갈라진 둘은
    틀린 하나보다 나쁘다 (11 §2.1)."""
    both = sorted(_sections("ONGOING.md") & _sections("DONE.md"))

    assert not both, f"ONGOING 과 DONE 에 모두 있다 — DONE 으로 옮겼으면 지운다: {both}"


def test_every_open_tag_has_detail_somewhere():
    """`[~]` 는 "열려 있다" 는 뜻이고, 열린 일에는 **이어받을 수 있는 세부**가 있어야 한다.

    진행 중이면 ONGOING, 끝났고 머지 대기면 DONE 이다. 둘 다 없으면 그 줄은
    한 줄 요약만 들고 있고, 짧은 줄은 틀려도 맞아 보인다.
    """
    detail = _sections("ONGOING.md") | _sections("DONE.md")
    naked = sorted(tag for tag, state in _tracked().items() if state == "~" and tag not in detail)

    assert not naked, f"`[~]` 인데 ONGOING · DONE 둘 다에 세부가 없다: {naked}"


def test_an_unstarted_tag_has_no_detail_anywhere():
    """`[ ]` 인데 세부가 있으면 체크박스가 거짓말을 하고 있다."""
    detail = _sections("ONGOING.md") | _sections("DONE.md")
    lying = sorted(tag for tag, state in _tracked().items() if state == " " and tag in detail)

    assert not lying, f"`[ ]` 인데 세부가 있다: {lying}"


def test_a_finished_tag_has_its_detail_in_done():
    detail = _sections("DONE.md")
    missing = sorted(tag for tag, state in _tracked().items() if state == "x" and tag not in detail)

    assert not missing, f"`[x]` 인데 DONE 에 세부가 없다: {missing}"


def test_every_ongoing_section_carries_dates_and_a_next_step():
    """날짜가 없으면 낡은 것이 안 보이고, 다음 걸음이 없으면 이어받을 수 없다."""
    text = (PLAN / "ONGOING.md").read_text(encoding="utf-8")
    blocks = re.split(r"^### (?=(?:M\d+-T\d+|H-\d+) ·)", text, flags=re.MULTILINE)[1:]
    bad = []
    for block in blocks:
        tag = block.split(" ·")[0]
        if not re.search(r"^시작 \d{4}-\d{2}-\d{2} · 갱신 \d{4}-\d{2}-\d{2}", block, re.MULTILINE):
            bad.append(f"{tag} — `시작 … · 갱신 …` 줄이 없다")
        if "**다음 걸음**" not in block:
            bad.append(f"{tag} — **다음 걸음** 이 없다")
        if "**전제**" not in block:
            bad.append(f"{tag} — **전제** 가 없다")
    assert not bad, "ONGOING 절의 형식이 어긋났다:\n  " + "\n  ".join(bad)
