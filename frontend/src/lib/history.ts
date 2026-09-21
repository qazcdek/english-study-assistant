import type { AnalysisState } from './analysis'

const KEY = 'eng-study:history'
const LIMIT = 30

export interface HistoryEntry {
  id: string
  text: string
  createdAt: number
  /** 서버 히스토리 목록에는 본문이 없어, 고를 때 따로 가져온다. */
  state: AnalysisState | null
}

export function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : []
  } catch {
    return []
  }
}

export function saveHistory(entries: HistoryEntry[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries.slice(0, LIMIT)))
  } catch {
    // 용량 초과 등은 조용히 무시한다 — 히스토리는 부가 기능이다.
  }
}

export function addEntry(entries: HistoryEntry[], state: AnalysisState): HistoryEntry[] {
  const entry: HistoryEntry = {
    id: crypto.randomUUID(),
    text: state.result.source_text,
    createdAt: Date.now(),
    state,
  }
  const next = [entry, ...entries.filter((e) => e.text !== entry.text)].slice(0, LIMIT)
  saveHistory(next)
  return next
}
