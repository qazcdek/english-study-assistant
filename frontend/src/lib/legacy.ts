import type { AnalysisResult, Expression, Overview, StructureNote } from './types'

/**
 * 브라우저에 저장된 옛 분석 기록을 지금 형식으로 올린다.
 *
 * 프롬프트를 손볼 때마다 결과 형식이 바뀌는데, localStorage 에는 그때그때의 형식으로
 * 남아 있다. TypeScript 타입은 런타임에 아무것도 검사하지 않으므로 화면이 깨지지는 않지만,
 * 필드 이름이 바뀐 자리는 **내용이 통째로 사라진 채** 그려진다.
 *
 * 웹 모드는 서버가 같은 일을 한다 (`backend/app/services/records.py`).
 */

/** 형식이 바뀔 때마다 올린다. 옛 기록에는 이 값이 없다. */
export const RESULT_VERSION = 3

interface LegacyStructure extends Partial<StructureNote> {
  fragment?: string
  /** 구문 해설이 한 칸이던 시절 */
  explanation?: string
}

interface LegacyOverview extends Partial<Overview> {
  /** 사용 빈도. 기준이 모호해 걷어냈다 */
  frequency?: string
}

type LegacyResult = Omit<Partial<AnalysisResult>, 'structures' | 'overview'> & {
  schema_version?: number
  structures?: LegacyStructure[]
  overview?: LegacyOverview | null
}

function upgradeStructure(item: LegacyStructure): StructureNote {
  if (typeof item.role === 'string') return item as StructureNote
  // 한 칸에 뭉쳐 있던 설명은 쪼갤 수 없다. 이 문장에서 하는 일 자리에 그대로 둔다.
  return {
    fragment: item.fragment ?? '',
    name: '',
    role: item.explanation ?? '',
    rewrite: '',
    pitfall: '',
  }
}

function upgradeOverview(item: LegacyOverview): Overview {
  const { frequency: _dropped, ...rest } = item
  return {
    domain: '',
    tone: '',
    formality: '중립',
    style: '혼합',
    key_expressions: [],
    comment: '',
    ...rest,
  } as Overview
}

export function upgradeResult(result: LegacyResult): AnalysisResult {
  if (result.schema_version === RESULT_VERSION) return result as AnalysisResult
  return {
    source_text: result.source_text ?? '',
    translation: result.translation ?? '',
    expressions: (result.expressions ?? []).map(
      (e): Expression => ({ ...e, nuance: e.nuance ?? '' }),
    ),
    structures: (result.structures ?? []).map(upgradeStructure),
    overview: result.overview ? upgradeOverview(result.overview) : null,
  }
}
