"""문서와 코드가 서로를 가리키는 주소를 한 곳에서 읽는다.

도달성 검사와 주소 검사가 같은 파서를 쓴다. 두 번 구현하면 두 검사가 서로 다른 것을
보게 되고, 그게 바로 11 2.1 이 금지하는 상태다.

**주소 표기 규약** (10 코드 규약 7절):

    09-mode-matrix.md          문서 전체를 가리킬 때
    09-mode-matrix.md §3.1     절을 가리킬 때

`documents/` 접두사와 `3.1절` 표기는 쓰지 않는다. 형태가 하나여야 기계가 읽는다.
"""

from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    """CLAUDE.md 가 있는 곳이 저장소 꼭대기다 (문서 계층의 뿌리이기도 하다)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "CLAUDE.md").is_file():
            return parent
    raise RuntimeError("CLAUDE.md 를 찾지 못했습니다. 저장소 밖에서 돌고 있습니다.")


ROOT = _repo_root()
ROOT_DOC = ROOT / "CLAUDE.md"

# 저장소에 속하지 않거나 생성물인 곳. 여기 파일은 세지 않는다.
SKIP_DIRS = {".git", "node_modules", ".venv", ".pytest_cache", "__pycache__", "dist", "build"}

HEADER_KEYS = ("층", "상태", "강제", "읽어야 할 때", "위", "아래", "함께")

_FENCE = re.compile(r"^\s*(?:```|~~~)")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
# 표준 마크다운 링크 [글자](주소) — 주소 뒤의 "제목" 은 버린다.
_LINK = re.compile(r"\[[^\]\n]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
_HEADING = re.compile(r"^#{2,6}\s+(\d+(?:\.\d+)*)\.?\s")
_DOC_NAME = re.compile(r"\d{2}-[a-z0-9-]+\.md")
_SECTION_AFTER = re.compile(r"^\s*§\s*(\d+(?:\.\d+)*)")
# 절 번호인데 § 가 없는 것 — "3.1절", "7 절", 그냥 " 3.1" 까지 전부.
_LEGACY_SECTION = re.compile(r"^\s+(\d+(?:\.\d+)*)\s*절?")


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def _in_repo(p: Path) -> bool:
    return not SKIP_DIRS & set(p.relative_to(ROOT).parts)


def all_docs() -> set[Path]:
    return {p.resolve() for p in ROOT.rglob("*.md") if _in_repo(p)}


def code_files() -> list[Path]:
    """주소를 들고 있을 수 있는 소스. 검사기 자신은 뺀다 — 설명문에 예시가 들어간다."""
    mine = {Path(__file__).resolve(), (Path(__file__).parent / "test_doc_references.py").resolve()}
    out = []
    for pattern in ("backend/app/**/*.py", "backend/tests/**/*.py", "frontend/src/**/*.ts*"):
        out += [p.resolve() for p in ROOT.glob(pattern) if _in_repo(p) and p.resolve() not in mine]
    return sorted(out)


def _outside_fences(text: str) -> list[tuple[int, str]]:
    """코드 블록 밖의 줄만 (1-기반 줄번호와 함께) 돌려준다."""
    lines, in_fence = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append((n, line))
    return lines


def links_in(doc: Path) -> list[str]:
    """인라인 코드도 뺀다 — 예시로 적어 둔 경로는 길이 아니다."""
    found: list[str] = []
    for _, line in _outside_fences(doc.read_text(encoding="utf-8")):
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


def sections_of(doc: Path) -> set[str]:
    """`## 3.` 과 `### 3.1` 에서 절 번호만 모은다."""
    text = doc.read_text(encoding="utf-8")
    return {m.group(1) for _, line in _outside_fences(text) if (m := _HEADING.match(line))}


def header_of(doc: Path) -> dict[str, str]:
    """제목 바로 아래 인용 블록의 `**키** 값` 들. 값 안에도 굵은 글씨가 있을 수 있으므로
    아는 키 이름만 칸의 시작으로 본다."""
    quote = []
    for line in doc.read_text(encoding="utf-8").splitlines():
        if line.startswith("> "):
            quote.append(line[2:])
        elif quote:
            break
    text = " ".join(quote)
    hits = [
        (m.start(), m.end(), m.group(1))
        for m in re.finditer(r"\*\*([^*]+)\*\*", text)
        if m.group(1) in HEADER_KEYS
    ]
    return {
        key: text[end : (hits[i + 1][0] if i + 1 < len(hits) else len(text))].strip(" ·")
        for i, (_, end, key) in enumerate(hits)
    }


class Ref(tuple):
    """코드 한 곳이 문서를 가리키는 주소 하나."""

    __slots__ = ()

    def __new__(cls, src: Path, line: int, doc: str, section: str | None, problem: str | None):
        return super().__new__(cls, (src, line, doc, section, problem))

    src, line, doc, section, problem = (property(lambda s, i=i: s[i]) for i in range(5))

    def where(self) -> str:
        return f"{rel(self.src)}:{self.line}"


def code_refs() -> list[Ref]:
    """소스가 들고 있는 문서 주소 전부. 규약에 어긋난 것은 problem 에 이유가 담긴다."""
    refs = []
    for src in code_files():
        for n, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
            for m in _DOC_NAME.finditer(line):
                after = line[m.end() :]
                section = problem = None
                if line[: m.start()].endswith("/"):
                    problem = "`documents/` 접두사를 쓰지 않는다"
                elif s := _SECTION_AFTER.match(after):
                    section = s.group(1)
                elif legacy := _LEGACY_SECTION.match(after):
                    problem = f"절은 `§{legacy.group(1)}` 로 적는다 (`{legacy.group(0).strip()}` 아님)"
                refs.append(Ref(src, n, m.group(0), section, problem))
    return refs
