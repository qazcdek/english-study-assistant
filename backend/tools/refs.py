"""한 문서(또는 한 절)로 **들어오는 참조**를 전수로 센다 — `./dev.sh refs`.

내용을 다른 문서로 옮길 때 "들어오는 참조를 확인했나" 를 기억에 맡기면 빠뜨린다.
실제로 07 §7 의 표를 14 로 옮기면서 사용자가 물었다 — **"참조가 필요한 경우 문서
링크를 추가했는지 확인해봐."** 그때 저장소 전체를 손으로 grep 했다. 그걸 명령으로 만든다.

검사(`test_doc_references.py`)는 **썩은 주소**를 잡지만, 옮기기 **전에** 무엇이
딸려 올지는 알려 주지 않는다. 이 도구는 고치기 전에 보는 쪽이다.

    ./dev.sh refs 14-data-layer.md          그 문서로 들어오는 전부
    ./dev.sh refs 07-web-deployment.md §7   그 절로 들어오는 것만
    ./dev.sh refs                           문서별 피참조 수
"""

from __future__ import annotations

import sys

from tests.docmap import ROOT, all_docs, code_refs, doc_refs, rel


def _inbound(doc: str, section: str | None):
    """(문서가 가리키는 것, 코드가 가리키는 것). 자기 자신은 세지 않는다."""
    wanted = [r for r in doc_refs() + code_refs() if r.doc == doc and r.src.name != doc]
    if section is not None:
        wanted = [r for r in wanted if r.section == section]
    return (
        sorted({(rel(r.src), r.line, r.section) for r in wanted if r.src.suffix == ".md"}),
        sorted({(rel(r.src), r.line, r.section) for r in wanted if r.src.suffix != ".md"}),
    )


def _census() -> str:
    """어느 문서가 얼마나 참조받나. 많이 받는 문서는 옮길 때 더 조심해야 한다."""
    counts: dict[str, int] = {}
    for ref in doc_refs() + code_refs():
        if ref.src.name != ref.doc:
            counts[ref.doc] = counts.get(ref.doc, 0) + 1
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    out = ["들어오는 참조 수 (많은 문서를 옮길 때 더 조심한다)", ""]
    out += [f"  {count:3}  {doc}" for doc, count in rows]
    return "\n".join(out)


def render(doc: str, section: str | None) -> str:
    from_docs, from_code = _inbound(doc, section)
    where = f"{doc}{f' §{section}' if section else ''}"
    total = len(from_docs) + len(from_code)
    if total == 0:
        return f"{where} 로 들어오는 참조가 없다. 옮겨도 딸려 오는 것이 없다."

    out = [f"{where} 로 들어오는 참조 {total}개", ""]
    for label, rows in (("문서", from_docs), ("코드", from_code)):
        if not rows:
            continue
        out.append(f"  {label}")
        for src, line, sec in rows:
            out.append(f"    {src}:{line}" + (f"  §{sec}" if sec else "  (문서 전체)"))
        out.append("")
    out.append("  옮긴다면 — 옮긴 자리에 길잡이를 남기거나, 위 참조를 새 주소로 고친다 (11 §3.6)")
    return "\n".join(out).rstrip()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(_census())
        return 0

    doc = argv[0].removeprefix("documents/")
    if doc not in {p.name for p in all_docs()}:
        print(f"그런 문서가 없다: {doc}", file=sys.stderr)
        print("  " + "\n  ".join(sorted(p.name for p in all_docs())), file=sys.stderr)
        return 1

    section = argv[1].lstrip("§") if len(argv) > 1 else None
    if section is not None:
        from tests.docmap import sections_of

        if section not in sections_of(ROOT / "documents" / doc):
            print(f"{doc} 에 §{section} 절이 없다", file=sys.stderr)
            return 1

    print(render(doc, section))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
