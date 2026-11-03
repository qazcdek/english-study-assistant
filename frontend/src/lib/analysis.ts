import { PART_FIELDS, type AnalysisResult, type PartField, type StreamEvent } from './types'
import type { AnalyzeMeta, MarkdownSections } from './types'

export type PartState = 'pending' | 'running' | 'done' | 'error'

export interface PartStatus {
  state: PartState
  elapsedMs?: number
  retried?: boolean
  error?: string
}

export interface AnalysisState {
  result: AnalysisResult
  markdown: Partial<Record<PartField, string>>
  status: Record<PartField, PartStatus>
  meta?: AnalyzeMeta
  fullMarkdown?: string
}

export const EMPTY_RESULT: AnalysisResult = {
  source_text: '',
  translation: '',
  expressions: [],
  structures: [],
  overview: null,
}

export function initialState(text: string): AnalysisState {
  return {
    result: { ...EMPTY_RESULT, source_text: text },
    markdown: {},
    status: {
      // 첫 파트는 요청과 동시에 시작된다.
      translation: { state: 'running' },
      expressions: { state: 'pending' },
      structures: { state: 'pending' },
      overview: { state: 'pending' },
    },
  }
}

/** 방금 끝난 파트 다음 것을 '진행 중'으로 올린다. */
function advance(status: AnalysisState['status'], index: number): AnalysisState['status'] {
  const next = PART_FIELDS[index + 1]
  if (!next || status[next].state !== 'pending') return status
  return { ...status, [next]: { state: 'running' } }
}

/** SSE 이벤트 하나를 현재 상태에 반영한다. */
export function reduce(state: AnalysisState, event: StreamEvent): AnalysisState {
  switch (event.type) {
    case 'part': {
      const status = advance(
        {
          ...state.status,
          [event.field]: {
            state: 'done',
            elapsedMs: event.elapsed_ms,
            retried: event.retried,
          },
        },
        event.index,
      )
      return {
        ...state,
        result: { ...state.result, ...event.data } as AnalysisResult,
        markdown: { ...state.markdown, [event.field]: event.markdown },
        status,
      }
    }
    case 'part_error': {
      const status = advance(
        { ...state.status, [event.field]: { state: 'error', error: event.message } },
        event.index,
      )
      return { ...state, status }
    }
    case 'done': {
      const status = { ...state.status }
      // 스트림이 중간에 끊겼다면 남은 파트를 실패로 마감한다.
      for (const field of PART_FIELDS) {
        if (status[field].state === 'pending' || status[field].state === 'running') {
          status[field] = { state: 'error', error: '가져오지 못했습니다.' }
        }
      }
      return {
        ...state,
        result: event.result,
        status,
        meta: event.meta,
        fullMarkdown: (event.markdown as MarkdownSections).full,
      }
    }
    case 'error':
      return {
        ...state,
        status: Object.fromEntries(
          PART_FIELDS.map((f) => [
            f,
            state.status[f].state === 'done'
              ? state.status[f]
              : { state: 'error' as const, error: event.message },
          ]),
        ) as AnalysisState['status'],
      }
  }
}

/**
 * **이미 끝난 분석**을 화면이 읽는 상태로 바꾼다.
 *
 * 두 곳이 같은 일을 한다 — 저장된 기록 하나를 열 때와 뉴스 문단을 펼칠 때.
 * 둘 다 네 파트가 이미 다 결정된 것을 받으므로 `reduce` 를 지나지 않는다.
 * 각자 짜면 한쪽만 고친 채로 갈라진다.
 *
 * **실패한 파트는 실패로 표시한다.** 전부 `done` 으로 칠하면 빈 칸이 "결과가
 * 없음" 처럼 보인다 — 미리 분석은 파트 하나가 실패해도 보여주기로 한 쪽이라
 * (`M13-T4`) 그 구별이 실제로 나타난다.
 */
export function finishedState(
  result: AnalysisResult,
  markdown: MarkdownSections,
  failedParts: readonly string[] = [],
): AnalysisState {
  const failed = new Set(failedParts)
  return {
    result,
    markdown,
    fullMarkdown: markdown.full,
    status: Object.fromEntries(
      PART_FIELDS.map((field) => [
        field,
        failed.has(field) ? { state: 'error', error: '가져오지 못했습니다.' } : { state: 'done' },
      ]),
    ) as AnalysisState['status'],
  }
}

export function isFinished(state: AnalysisState): boolean {
  return PART_FIELDS.every((f) => state.status[f].state === 'done' || state.status[f].state === 'error')
}
