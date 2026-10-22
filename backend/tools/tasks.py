"""열린 작업을 한 곳에 모아 보여준다 — `./dev.sh next`.

무엇부터 할지 고를 때 두 문서를 따로 훑으면 반드시 한쪽을 빼먹는다. 실제로 그랬다:
머지가 끝난 뒤에도 `[~]` 네 개가 그대로 남아 있었고 아무도 몰랐다 (H-018).

**표시 순서는 우선순위가 아니라 규칙이다.**

1. `[~]` 먼저. "끝났고 머지 대기" 라고 선언된 것이므로 **가장 싸게 닫히고 가장 쉽게 잊힌다.**
   DONE 에 세부가 있으면 머지됐는지부터 확인하라는 뜻이다.
2. 그다음 `H`. 지금 동작이 잘못된 것이 아직 안 만든 것보다 앞선다.
3. 그다음 `M`-`T`, 마일스톤 번호 순.

`[~]` 는 **사람에게 묻지 않고 git 에 묻는다.** "머지됐는지 확인하라" 는 안내는
지켜지지 않았다 — 머지가 브랜치 끝을 안 담아 배포본이 반쪽이 됐고, 화면에는
"예문이 없어 직접 써보기를 할 수 없습니다" 만 남았다 (H-022). 선언이 아니라 장치여야 한다.

무엇을 **먼저 할지는 사람이 정한다.** 이 도구는 빠진 것이 없게만 한다.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field

from tools import docptr
from tools.docptr import DOCS, scan_docs

PLAN = DOCS / "plan"
# `[~]` 가 머지됐는지 재는 기준. 배포는 여기서 나간다.
BASE_REFS = ("origin/main", "main")
# 기준 ref 가 없을 때. 얕은 클론(CI)에는 origin/main 이 없다.
NO_BASE = "기준 ref 가 없어 재지 못했다 — `git fetch origin main` 뒤에 다시 본다"
# 태그가 아닌 자리. base 가 낡았다는 알림을 `reports` 에 같이 실어 보낸다.
_BASE_KEY = "__base__"
_SEP, _REC = "\x1f", "\x1e"
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


# --- `[~]` 가 정말 머지됐는지 ---------------------------------------------------
#
# 규약이 커밋 메시지 끝줄에 태그를 달게 하므로(CLAUDE.md 5절 6항), 태그로 커밋을
# 되찾을 수 있다. 머지 커밋은 태그를 안 담으므로 **브랜치 커밋 자체**를 본다.
# 바로 그래서 "끝을 안 담은 머지" 가 잡힌다.


def tag_commits(tag: str, history: list[tuple[str, str]]) -> list[str]:
    """메시지에 이 태그가 박힌 커밋들. `H-02` 가 `H-021` 을 긁지 않게 경계를 둔다."""
    pattern = re.compile(rf"(?<![0-9A-Za-z-]){re.escape(tag)}(?![0-9A-Za-z-])")
    return [sha for sha, message in history if pattern.search(message)]


def merge_report(tag: str, history: list[tuple[str, str]], base: str, shipped: set[str]) -> str:
    """`[~]` 한 줄에 붙일 한 문장. 저장소를 안 건드리는 순수 함수라 검사하기 쉽다.

    **머지됐다는 사실만 찍고 닫으라고 명령하지 않는다.** 머지됐어도 실측이 남아
    못 닫는 줄이 있다(H-021). 닫을 때인지는 사람이 안다.
    """
    commits = tag_commits(tag, history)
    if not commits:
        return "커밋을 못 찾았다 — 아직 안 올라갔거나 메시지에 태그가 없다"
    missing = [sha for sha in commits if sha not in shipped]
    if not missing:
        return f"{base} 에 커밋 {len(commits)}개 전부 들어갔다 — 남은 이유가 없으면 [x] 로"
    return (
        f"{base} 에 커밋 {len(missing)}/{len(commits)}개가 없다 — "
        f"머지가 끝을 안 담았다: " + " ".join(sha[:9] for sha in missing)
    )


def _git(*args: str) -> str | None:
    """실패를 예외로 올리지 않는다. git 이 없는 자리에서도 목록은 나와야 한다."""
    try:
        done = subprocess.run(
            ("git", "-C", str(docptr.ROOT), *args),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def commit_log() -> list[tuple[str, str]] | None:
    """모든 커밋의 (해시, 메시지). git 을 못 읽으면 `None`."""
    log = _git("log", "--all", f"--format=%H{_SEP}%B{_REC}")
    if log is None:
        return None
    history = []
    for record in log.split(_REC):
        if sha_message := record.strip("\n"):
            sha, _, message = sha_message.partition(_SEP)
            history.append((sha, message))
    return history


def base_ref() -> str | None:
    """머지됐는지 재는 기준. 없을 수 있다 — 얕은 클론에는 `origin/main` 이 없다."""
    return next((ref for ref in BASE_REFS if _git("rev-parse", "--verify", ref) is not None), None)


def stale_message(base: str, count: int) -> str | None:
    """base 가 몇 커밋 앞서 있는지를 한 문장으로. 앞서 있지 않으면 아무 말도 안 한다.

    저장소를 안 건드리는 순수 함수라 검사하기 쉽다.
    """
    if count <= 0:
        return None
    return (
        f"  {base} 가 {count}커밋 앞서 있다 — 합치고 시작한다 "
        f"(`git fetch && git merge {base}`).\n"
        "  낡은 base 에서 갈라지면 ROADMAP · ISSUES 가 충돌한다"
    )


def behind_base() -> str | None:
    """기준 ref 가 내 브랜치보다 앞서 있으면 몇 커밋인지.

    **낡은 base 에서 갈라져 나온 것이 충돌의 진짜 원인이다.** 추적 문서는 같은 줄의
    체크박스가 바뀌는 파일이라, main 이 어떤 태그를 `[x]` 로 올린 뒤에 내가 그 옆에
    줄을 더하면 git 은 겹친 변경으로 본다. 네 번 났다 (H-026).

    `./dev.sh next` 는 **일을 시작하기 전에** 부르는 명령이다. 그 자리가 "base 가
    낡았다" 고 말해 줄 유일하게 맞는 자리다 — 충돌을 본 뒤가 아니라 그 전이다.
    네트워크는 몰래 치지 않는다. 마지막으로 가져온 ref 를 그대로 본다.
    """
    base = base_ref()
    if base is None:
        return None
    out = _git("rev-list", "--count", f"HEAD..{base}")
    if out is None or not out.strip().isdigit():
        return None
    return stale_message(base, int(out.strip()))


def merge_reports(tags: list[str]) -> dict[str, str]:
    """`[~]` 태그마다 한 문장. **빈 칸을 돌려주는 경우는 git 자체가 없을 때뿐이다.**

    기준 ref 가 없을 때 빈 칸을 돌려주면 화면이 "머지됐는지 확인하라" 는 옛 문구로
    떨어진다. 그건 장치가 아니라 부탁이고, 이 도구는 그 부탁을 없애려고 만들었다.
    **잴 수 없으면 잴 수 없다고 말한다.** 실제로 CI 의 얕은 클론에서 이렇게 조용히
    꺼졌다 (H-022).
    """
    history = commit_log()
    if history is None:
        return {}
    base = base_ref()
    if base is None:
        return dict.fromkeys(tags, NO_BASE)
    shipped = _git("rev-list", base)
    if shipped is None:
        return {}
    return {tag: merge_report(tag, history, base, set(shipped.split())) for tag in tags}


def render(
    tasks: list[Task],
    prefix: str | None = None,
    reports: dict[str, str] | None = None,
) -> str:
    reports = reports or {}
    open_tasks = [t for t in tasks if t.state != "x"]
    if prefix:
        open_tasks = [t for t in open_tasks if t.tag.startswith(prefix.upper())]

    out: list[str] = []
    waiting = [t for t in open_tasks if t.state == "~"]
    if waiting:
        out.append(f"머지 대기 — 끝났다고 선언된 것부터 확인한다 ({len(waiting)})")
        out += _block(waiting, reports)
        if any("끝을 안 담았다" in reports.get(t.tag, "") for t in waiting):
            # 기준 ref 는 마지막으로 가져온 시점의 것이다. 오래됐으면 틀릴 수 있다.
            out.append("\n  최신이 아닐 수 있다 — `git fetch` 뒤에 다시 본다")
        out.append("")

    if stale := reports.get(_BASE_KEY):
        out.append(stale)
        out.append("")

    todo = [t for t in open_tasks if t.state == " "]
    out.append(f"열린 작업 ({len(todo)})")
    out += _block(todo, reports) if todo else ["  없음"]

    if not open_tasks:
        return f"열린 작업이 없다{f' ({prefix})' if prefix else ''}."
    return "\n".join(out)


def _block(tasks: list[Task], reports: dict[str, str]) -> list[str]:
    out, section = [], None
    for task in tasks:
        where = f"{task.doc.removesuffix('.md')} · {task.section}"
        if where != section:
            section, _ = where, out.append(f"\n  {where}")
        out.append(f"    {task.tag:9} {task.summary}")
        for target in task.pointers:
            out.append(f"              → {target}")
        if task.state != "~":
            continue
        if report := reports.get(task.tag):
            out.append(f"              {report}")
        elif task.has_detail:
            out.append("              DONE 에 세부 있음 — 머지됐는지 확인하고 [x] 로 올린다")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    prefix = argv[0] if argv else None
    if bad := malformed_task_lines():
        print("태스크 줄 형태가 규약과 다르다:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    tasks = scan_tasks()
    waiting = [t.tag for t in tasks if t.state == "~"]
    reports = merge_reports(waiting) if waiting else {}
    if stale := behind_base():
        reports[_BASE_KEY] = stale
    print(render(tasks, prefix, reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
