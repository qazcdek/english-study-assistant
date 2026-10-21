"""문서 → 코드 포인터를 읽어 코드 쪽 역참조를 생성한다.

**방향이 핵심이다.** 사람이 손으로 적는 것은 문서 쪽 하나뿐이고, 코드 docstring 의
`[문서]` 줄은 전부 이 도구가 만든다. 양쪽을 동시에 고치라고 부탁하면 한쪽은 반드시
빠지기 때문이다 (11-docs-architecture.md §2.3).

문서 쪽 표기 — 인라인 코드 안에 화살표와 주소를 적는다::

    `→ backend/app/config.py`                              모듈
    `→ backend/app/config.py::Settings`                    클래스
    `→ backend/app/routers/analyze.py::max_input_chars`    함수
    `→ backend/app/config.py::Settings.local_max_input_chars`

**줄 번호를 쓰지 않는다.** 주소는 AST 로 푼다. 코드를 위아래로 옮기거나 import 를
더해도 포인터는 길을 잃지 않는다. 이름을 바꾸면 그때는 **실패해야 맞다** — 가리키던
것이 실제로 없어졌으니까.

코드 쪽 결과 (도구가 씀, 손대지 말 것)::

    def max_input_chars(...):
        \"\"\"모드별 입력 상한. 스키마의 절대 상한보다 좁다.

        [문서] 09-mode-matrix.md §3.1
        [문서] plan/DONE.md H-017
        \"\"\"

사용::

    python tools/docptr.py            검사만 한다 (CI 용). 갱신이 필요하면 1 로 끝난다
    python tools/docptr.py --write    코드 쪽을 실제로 고친다
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MARKER = "[문서]"
# 자기 자신과 자기 테스트는 건드리지 않는다. 설명문에 마커 예시가 들어가기 때문이다.
SELF = {"backend/tools/docptr.py", "backend/tests/test_docptr.py"}

# 문서가 코드를 가리키는 표기: 인라인 코드 안의 `→ 경로::qualname`
_POINTER = re.compile(r"`\s*→\s*([\w./-]+\.py)(?:::([\w.]+))?\s*`")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")
_TAGGED = re.compile(r"^(M\d+-T\d+|H-\d+)\b")
# 진행 문서는 제목이 아니라 목록 항목에 태그가 붙는다: `- [x] H-012  ...`
_ITEM_TAG = re.compile(r"^\s*[-*]\s+(?:\[.\]\s+)?(M\d+-T\d+|H-\d+)\b")


def repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "CLAUDE.md").is_file():
            return parent
    raise RuntimeError("CLAUDE.md 를 찾지 못했습니다.")


ROOT = repo_root()
DOCS = ROOT / "documents"


@dataclass(frozen=True, order=True)
class Pointer:
    """문서 한 줄이 코드 한 심벌을 가리키는 포인터."""

    target: str  # "backend/app/config.py::Settings"
    doc: str  # "plan/DONE.md"
    label: str  # "§3.1" 또는 "H-017" 또는 제목 글자
    doc_line: int

    @property
    def path(self) -> str:
        return self.target.split("::")[0]

    @property
    def qualname(self) -> str | None:
        return self.target.split("::")[1] if "::" in self.target else None

    def marker(self) -> str:
        return f"{MARKER} {self.doc} {self.label}".rstrip()


def _label_for(heading: str) -> str:
    """가장 가까운 제목을 짧은 꼬리표로 줄인다. 번호가 있으면 §번호가 제일 안정적이다."""
    if m := _NUMBERED.match(heading):
        return f"§{m.group(1)}"
    if m := _TAGGED.match(heading):
        return m.group(1)
    return heading[:40].strip()


def scan_docs() -> list[Pointer]:
    """documents/ 전체에서 문서 → 코드 포인터를 긁는다."""
    found: list[Pointer] = []
    for doc in sorted(DOCS.rglob("*.md")):
        heading, tag, in_fence = "", "", False
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            # 코드 블록 안은 설명용 예시다. 규약 자체를 적은 문서가 자기 예시를 가리키게
            # 되면 안 된다.
            if _FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if m := _HEADING.match(line):
                heading, tag = m.group(1).strip(), ""
                continue
            if m := _ITEM_TAG.match(line):
                tag = m.group(1)
            for hit in _POINTER.finditer(line):
                path, qualname = hit.group(1), hit.group(2)
                found.append(
                    Pointer(
                        target=f"{path}::{qualname}" if qualname else path,
                        doc=str(doc.relative_to(DOCS)),
                        label=tag or _label_for(heading),
                        doc_line=n,
                    )
                )
    return found


# --------------------------------------------------------------- AST 로 주소 풀기

_HAS_DOC = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _walk(node: ast.AST, prefix: str = "") -> dict[str, ast.AST]:
    """docstring 을 가질 수 있는 심벌의 qualname → 노드. 변수는 담지 않는다 —
    붙일 자리가 없으면 포인터를 달 수 없기 때문이다 (감싸는 클래스를 가리키면 된다)."""
    table: dict[str, ast.AST] = {}
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            name = f"{prefix}{child.name}"
            table[name] = child
            table |= _walk(child, f"{name}.")
    return table


def symbols_of(source: str) -> dict[str | None, ast.AST]:
    """None 은 모듈 자신을 가리킨다."""
    tree = ast.parse(source)
    return {None: tree, **_walk(tree)}


# ------------------------------------------------------------ docstring 고쳐 쓰기


def _docstring_node(node: ast.AST) -> ast.Expr | None:
    body = getattr(node, "body", [])
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[0]
    return None


def _render(text: str, markers: list[str]) -> str:
    """docstring 본문에서 옛 `[문서]` 줄을 걷어내고 새 것을 끝에 붙인다."""
    kept = [ln for ln in text.splitlines() if not ln.strip().startswith(MARKER)]
    while kept and not kept[-1].strip():
        kept.pop()
    if markers:
        kept += ([""] if kept else []) + markers
    return "\n".join(kept)


def apply_to_file(path: Path, wanted: dict[str | None, list[str]]) -> str | None:
    """이 파일에 필요한 마커를 반영한 소스를 돌려준다. 바뀔 게 없으면 None."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    table = symbols_of(source)

    # 뒤에서부터 고쳐야 앞쪽 줄 번호가 밀리지 않는다.
    edits: list[tuple[int, int, list[str]]] = []
    for qualname, node in table.items():
        markers = sorted(set(wanted.get(qualname, [])))
        doc_expr = _docstring_node(node)

        if doc_expr is None:
            if not markers:
                continue
            body = getattr(node, "body", [])
            if not body:
                continue
            indent = " " * body[0].col_offset
            block = [f'{indent}"""', *[f"{indent}{m}" for m in markers], f'{indent}"""']
            edits.append((body[0].lineno - 1, body[0].lineno - 1, block))
            continue

        start, end = doc_expr.lineno - 1, doc_expr.end_lineno
        raw = "\n".join(lines[start:end])
        quote = '"""' if '"""' in raw else "'''"
        indent = " " * doc_expr.col_offset
        inner = doc_expr.value.value
        body_text = _render(inner, [f"{indent}{m}" for m in markers])

        if body_text.strip() and "\n" not in body_text.strip() and not markers:
            block = [f"{indent}{quote}{body_text.strip()}{quote}"]
        else:
            first, *rest = body_text.split("\n") if body_text else [""]
            block = [f"{indent}{quote}{first.lstrip() if not rest else first.strip()}"]
            block += rest
            block.append(f"{indent}{quote}")
        if block != lines[start:end]:
            edits.append((start, end, block))

    if not edits:
        return None
    for start, end, block in sorted(edits, reverse=True):
        lines[start:end] = block
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------ 실행


def collect() -> tuple[dict[Path, dict[str | None, list[str]]], list[str]]:
    """포인터를 파일별로 모으고, 풀리지 않는 주소를 함께 돌려준다."""
    wanted: dict[Path, dict[str | None, list[str]]] = {}
    problems: list[str] = []
    for ptr in scan_docs():
        path = ROOT / ptr.path
        where = f"documents/{ptr.doc}:{ptr.doc_line}"
        if not path.is_file():
            problems.append(f"{where}  없는 파일 {ptr.path}")
            continue
        try:
            table = symbols_of(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"{where}  {ptr.path} 를 읽을 수 없다 ({exc})")
            continue
        if ptr.qualname not in table:
            problems.append(f"{where}  {ptr.path} 에 `{ptr.qualname}` 이 없다")
            continue
        wanted.setdefault(path, {}).setdefault(ptr.qualname, []).append(ptr.marker())
    return wanted, problems


def run(write: bool) -> int:
    wanted, problems = collect()

    # 문서가 더 이상 가리키지 않는 파일에 마커가 남아 있을 수 있다. 그것도 지운다.
    stale = [
        p
        for p in sorted(ROOT.rglob("*.py"))
        if not {".venv", "node_modules", "__pycache__", ".git"} & set(p.parts)
        and str(p.relative_to(ROOT)) not in SELF
        and p not in wanted
        and MARKER in p.read_text(encoding="utf-8")
    ]
    for path in stale:
        wanted[path] = {}

    changed = []
    for path, table in sorted(wanted.items()):
        if (new := apply_to_file(path, table)) is not None:
            changed.append(path.relative_to(ROOT))
            if write:
                path.write_text(new, encoding="utf-8")

    for line in problems:
        print(f"  주소가 풀리지 않는다  {line}", file=sys.stderr)
    if changed:
        verb = "고쳤다" if write else "갱신이 필요하다"
        print(f"  {verb}: " + " · ".join(str(c) for c in changed), file=sys.stderr)
    if problems or (changed and not write):
        if not write:
            print("  → python tools/docptr.py --write", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="문서 → 코드 포인터를 코드에 반영한다")
    parser.add_argument("--write", action="store_true", help="코드 docstring 을 실제로 고친다")
    return run(parser.parse_args().write)


if __name__ == "__main__":
    raise SystemExit(main())
