import type { AnalysisState } from './analysis'
import type { Level } from './types'

/**
 * 최근 분석 목록의 한 줄.
 *
 * 기록은 두 모드 모두 서버(Postgres)에 있다. 목록에는 본문이 없어 고를 때 따로 가져온다.
 */
export interface HistoryEntry {
  id: string
  text: string
  createdAt: number
  state: AnalysisState | null
  level?: Level
}
