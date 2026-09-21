"""분석 결과(JSON) → 마크다운 변환.

LLM에는 JSON만 요구하고, 표 정렬·라벨·섹션 순서 같은 표현 규칙은 여기서 코드로 고정한다.
모델을 바꿔도 출력 모양이 흔들리지 않게 하기 위한 의도적인 분리다.
"""

from app.schemas import (
    AnalysisResult,
    Expression,
    MarkdownSections,
    Overview,
    StructureNote,
)

SECTION_SEPARATOR = "\n\n---\n\n"
FAILED_NOTE = "_이 항목을 가져오지 못했습니다._"


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _cell(value: str) -> str:
    """표 셀 안에서 깨지는 문자를 정리한다."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def render_translation(translation: str) -> str:
    body = translation.strip() or FAILED_NOTE
    return f"### 자연스러운 번역\n\n{body}"


def render_expressions(expressions: list[Expression]) -> str:
    lines = ["### 표현 풀이", ""]
    if not expressions:
        lines.append("_따로 짚을 만한 표현이 없습니다._")
        return "\n".join(lines)

    has_example = any(e.example for e in expressions)
    header = ["표현 (영어)", "유형", "의미 및 설명"]
    if has_example:
        header.append("예문")

    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")

    for e in expressions:
        row = [f"**{_cell(e.expression)}**", _cell(e.type), _cell(e.meaning)]
        if has_example:
            row.append(_cell(e.example or "—"))
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def render_structures(structures: list[StructureNote]) -> str:
    lines = ["### 문장 구조", ""]
    if not structures:
        lines.append("_특별히 설명할 구문이 없습니다._")
        return "\n".join(lines)

    for i, s in enumerate(structures):
        if i:
            lines.append("")
        lines.append(f"* **{s.fragment.strip()}** — {s.name.strip()}")
        lines.append(f"  * {_one_line(s.role)}")
        if s.rewrite.strip():
            lines.append(f"  * 쉽게 쓰면: `{_one_line(s.rewrite)}`")
        if s.pitfall.strip():
            lines.append(f"  * 주의: {_one_line(s.pitfall)}")

    return "\n".join(lines)


def render_overview(overview: Overview | None) -> str:
    if overview is None:
        return f"### 총평\n\n{FAILED_NOTE}"

    lines = [
        "### 총평",
        "",
        f"* **분야**: {overview.domain}",
        f"* **톤**: {overview.tone}",
        f"* **격식 수준**: {overview.formality}",
        f"* **문체**: {overview.style}",
    ]
    if overview.key_expressions:
        picked = ", ".join(f"`{e}`" for e in overview.key_expressions)
        lines += ["", f"**꼭 챙길 표현**: {picked}"]
    lines += ["", overview.comment.strip()]
    return "\n".join(lines)


# 파트 필드명 → 렌더러. AnalyzerService 가 파트를 받는 즉시 이걸로 조각을 만든다.
RENDERERS = {
    "translation": render_translation,
    "expressions": render_expressions,
    "structures": render_structures,
    "overview": render_overview,
}


def render_part(field: str, value) -> str:
    return RENDERERS[field](value)


def render(result: AnalysisResult) -> MarkdownSections:
    translation = render_translation(result.translation)
    expressions = render_expressions(result.expressions)
    structures = render_structures(result.structures)
    overview = render_overview(result.overview)
    full = SECTION_SEPARATOR.join([translation, expressions, structures, overview])
    return MarkdownSections(
        translation=translation,
        expressions=expressions,
        structures=structures,
        overview=overview,
        full=full,
    )
