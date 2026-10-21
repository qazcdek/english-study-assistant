"""도달성 검사 — 꼭대기(CLAUDE.md)에서 모든 문서에 실제로 닿는지 본다.

색인에 **이름이 적혀 있는지** 보는 것으로는 부족하다. 적혀 있어도 링크가 아닐 수 있고,
링크여도 꼭대기에서 그 문서까지 가는 길 중간이 끊겨 있을 수 있다. 특히 CLAUDE.md 에서
색인으로 가는 링크 하나만 지워도 모든 문서가 통째로 떨어져 나가는데, 각 문서는 여전히
`위` 를 달고 있고 색인에도 등록되어 있어서 **글자만 보는 검사는 전부 통과한다.**

그래서 표준 마크다운 링크로 그래프를 만들고 꼭대기에서 직접 걸어 본다.
규약은 11-docs-architecture.md §2.2 · §3.1. 파서는 docmap.py 한 곳에 있다.
"""

from __future__ import annotations

from collections import deque

import pytest

from tests.docmap import ROOT_DOC, all_docs, edges_of, rel


@pytest.fixture(scope="module")
def docs() -> set:
    return all_docs()


def test_the_document_set_was_actually_found(docs):
    """셋이 비면 아래 검사가 전부 조용히 통과한다. 먼저 못을 박는다."""
    assert ROOT_DOC in docs, "CLAUDE.md 가 문서 목록에 없습니다"
    assert len(docs) >= 10, f"문서를 {len(docs)}개밖에 못 찾았습니다. 수집이 깨졌습니다"


def test_no_markdown_link_points_at_a_missing_file(docs):
    broken = [
        f"{rel(src)} → {raw}"
        for src in sorted(docs)
        for raw, target in edges_of(src)
        if not target.is_file()
    ]
    assert not broken, "끊긴 링크:\n  " + "\n  ".join(broken)


def test_every_document_is_reachable_from_claude_md(docs):
    """꼭대기에서 걸어서 닿지 않는 문서는 아무도 읽지 않는다."""
    seen = {ROOT_DOC}
    queue = deque([ROOT_DOC])
    while queue:
        for _, target in edges_of(queue.popleft()):
            if target in docs and target not in seen:
                seen.add(target)
                queue.append(target)

    unreachable = sorted(rel(p) for p in docs - seen)
    assert not unreachable, (
        "CLAUDE.md 에서 닿지 않는 문서:\n  "
        + "\n  ".join(unreachable)
        + "\n색인(00-index.md)에 등록하고, 그 문서 머리말에 `위` 를 답니다."
    )
