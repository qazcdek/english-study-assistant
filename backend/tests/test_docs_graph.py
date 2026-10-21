"""문서 링크 그래프 — 꼭대기(CLAUDE.md)에서 모든 문서에 실제로 닿는지 본다.

색인에 **이름이 적혀 있는지** 보는 것으로는 부족하다. 적혀 있어도 링크가 아닐 수 있고,
링크여도 꼭대기에서 그 문서까지 가는 길 중간이 끊겨 있을 수 있다. 특히 CLAUDE.md 에서
색인으로 가는 링크 하나만 지워도 모든 문서가 통째로 떨어져 나가는데, 각 문서는 여전히
`위` 를 달고 있고 색인에도 등록되어 있어서 **글자만 보는 검사는 전부 통과한다.**

그래서 표준 마크다운 링크로 그래프를 만들고 꼭대기에서 직접 걸어 본다.
규약은 documents/11-docs-architecture.md 2.2 · 3.1.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path

import pytest


def _repo_root() -> Path:
    """CLAUDE.md 가 있는 곳이 저장소 꼭대기다 (문서 계층의 뿌리이기도 하다)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "CLAUDE.md").is_file():
            return parent
    raise RuntimeError("CLAUDE.md 를 찾지 못했습니다. 저장소 밖에서 돌고 있습니다.")


ROOT = _repo_root()
ROOT_DOC = ROOT / "CLAUDE.md"

# 저장소에 속하지 않거나 생성물인 곳. 여기 .md 는 문서가 아니다.
SKIP_DIRS = {".git", "node_modules", ".venv", ".pytest_cache", "__pycache__", "dist", "build"}

_FENCE = re.compile(r"^\s*(?:```|~~~)")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
# 표준 마크다운 링크 [글자](주소) — 주소 뒤의 "제목" 은 버린다.
_LINK = re.compile(r"\[[^\]\n]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")


def all_docs() -> set[Path]:
    return {
        p.resolve()
        for p in ROOT.rglob("*.md")
        if not SKIP_DIRS & set(p.relative_to(ROOT).parts)
    }


def links_in(doc: Path) -> list[str]:
    """코드 블록과 인라인 코드는 뺀다 — 예시로 적어 둔 경로는 길이 아니다."""
    found: list[str] = []
    in_fence = False
    for line in doc.read_text(encoding="utf-8").splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            found += _LINK.findall(_INLINE_CODE.sub("", line))
    return found


def edges_of(doc: Path) -> list[tuple[str, Path]]:
    """이 저장소의 다른 .md 를 가리키는 링크만 간선으로 센다."""
    out = []
    for raw in links_in(doc):
        if "://" in raw or raw.startswith(("mailto:", "#")):
            continue
        target = raw.split("#", 1)[0]
        if target.endswith(".md"):
            out.append((raw, (doc.parent / target).resolve()))
    return out


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


@pytest.fixture(scope="module")
def docs() -> set[Path]:
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
        + "\n색인(documents/00-index.md)에 등록하고, 그 문서 머리말에 `위` 를 답니다."
    )
