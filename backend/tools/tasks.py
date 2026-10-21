"""열린 작업을 한 곳에 모아 보여준다 — `./dev.sh next`.

무엇부터 할지 고를 때 두 문서를 따로 훑으면 반드시 한쪽을 빼먹는다. 실제로 그랬다:
머지가 끝난 뒤에도 `[~]` 네 개가 그대로 남아 있었고 아무도 몰랐다 (H-018).

**표시 순서는 우선순위가 아니라 규칙이다.**

1. `[~]` 먼저. "끝났고 머지 대기" 라고 선언된 것이므로 **가장 싸게 닫히고 가장 쉽게 잊힌다.**
   DONE 에 세부가 있으면 머지됐는지부터 확인하라는 뜻이다.
2. 그다음 `H`. 지금 동작이 잘못된 것이 아직 안 만든 것보다 앞선다.
3. 그다음 `M`-`T`, 마일스톤 번호 순.

무엇을 **먼저 할지는 사람이 정한다.** 이 도구는 빠진 것이 없게만 한다.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

from tools.docptr import DOCS, scan_docs

PLAN = DOCS / "plan"
# `- [x] M1-T5  요약` / `- [ ] H-018  요약`
_TASK = re.compile(r"^- \[( |~|x)\]\s+(M\d+-T\d+|H-\d+)\s+(.*)$")
_HEADING = re.compile(r"^##\s+(.*)$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_MILESTONE = re.compile(r"^M(\d+)")


@dataclass
class Task:
    tag: str
    state: str  # " " | "~" | "x"
    summary: str
    doc: str  # "ROADMAP.md"
    section: str  # 속한 ## 제목
    line: int
    pointers: list[str] = field(default_factory=list)
    has_detail: bool = False

    @property
    def kind(self) -> str:
        return "H" if self.tag.startswith("H-") else "M"

    def sort_key(self) -> tuple:
        """표시 순서 규칙. 모듈 설명 참고."""
        state_rank = {"~": 0, " ": 1, "x": 2}[self.state]
        if self.kind == "H":
            return (state_rank, 0, 0, int(self.tag.split("-")[1]))
        milestone, task = (int(n) for n in self.tag[1:].split("-T"))
        return (state_rank, 1, milestone, task)


def scan_tasks() -> list[Task]:
    """ROADMAP 과 ISSUES 의 모든 태스크 줄. 코드 포인터와 DONE 세부 여부를 함께 붙인다."""
    by_tag: dict[str, list[str]] = {}
    for ptr in scan_docs():
        by_tag.setdefault(ptr.label, []).append(ptr.target)
    done = (PLAN / "DONE.md").read_text(encoding="utf-8")

    tasks: list[Task] = []
    for name in ("ROADMAP.md", "ISSUES.md"):
        doc = PLAN / name
        section, in_fence = "", False
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if _FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if m := _HEADING.match(line):
                section = m.group(1).strip()
            elif m := _TASK.match(line):
                state, tag, summary = m.groups()
                tasks.append(
                    Task(
                        tag=tag,
                        state=state,
                        summary=summary.strip(),
                        doc=name,
                        section=section,
                        line=n,
                        pointers=sorted(by_tag.get(tag, [])),
                        has_detail=f"### {tag} " in done,
                    )
                )
    return sorted(tasks, key=Task.sort_key)


def malformed_task_lines() -> list[str]:
    """태스크처럼 보이는데 규약 형태가 아닌 줄. 이런 줄은 도구에 안 잡혀 조용히 사라진다."""
    bad = []
    for name in ("ROADMAP.md", "ISSUES.md"):
        doc = PLAN / name
        in_fence = False
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if _FENCE.match(line):
                in_fence = not in_fence
                continue
            if not in_fence and line.startswith("- [") and not _TASK.match(line):
                bad.append(f"plan/{name}:{n}  {line.strip()}")
    return bad


def render(tasks: list[Task], prefix: str | None = None) -> str:
    open_tasks = [t for t in tasks if t.state != "x"]
    if prefix:
        open_tasks = [t for t in open_tasks if t.tag.startswith(prefix.upper())]

    out: list[str] = []
    waiting = [t for t in open_tasks if t.state == "~"]
    if waiting:
        out.append(f"머지 대기 — 끝났다고 선언된 것부터 확인한다 ({len(waiting)})")
        out += _block(waiting)
        out.append("")

    todo = [t for t in open_tasks if t.state == " "]
    out.append(f"열린 작업 ({len(todo)})")
    out += _block(todo) if todo else ["  없음"]

    if not open_tasks:
        return f"열린 작업이 없다{f' ({prefix})' if prefix else ''}."
    return "\n".join(out)


def _block(tasks: list[Task]) -> list[str]:
    out, section = [], None
    for task in tasks:
        where = f"{task.doc.removesuffix('.md')} · {task.section}"
        if where != section:
            section, _ = where, out.append(f"\n  {where}")
        out.append(f"    {task.tag:9} {task.summary}")
        for target in task.pointers:
            out.append(f"              → {target}")
        if task.state == "~" and task.has_detail:
            out.append("              DONE 에 세부 있음 — 머지됐는지 확인하고 [x] 로 올린다")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    prefix = argv[0] if argv else None
    if bad := malformed_task_lines():
        print("태스크 줄 형태가 규약과 다르다:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    print(render(scan_tasks(), prefix))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
