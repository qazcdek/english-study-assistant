import type { AnalysisState } from './analysis'
import type { Level } from './types'

const KEY = 'eng-study:history'
const LIMIT = 30

export interface HistoryEntry {
  id: string
  text: string
  createdAt: number
  state: AnalysisState
  /** 예전에 저장된 항목에는 없다. 목록에서 표시를 생략한다. */
  level?: Level
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

export function removeEntry(entries: HistoryEntry[], id: string): HistoryEntry[] {
  const next = entries.filter((e) => e.id !== id)
  saveHistory(next)
  return next
}

export function addEntry(
  entries: HistoryEntry[],
  state: AnalysisState,
  level: Level,
): HistoryEntry[] {
  const entry: HistoryEntry = {
    id: crypto.randomUUID(),
    text: state.result.source_text,
    createdAt: Date.now(),
    state,
    level,
  }
  const next = [entry, ...entries.filter((e) => e.text !== entry.text)].slice(0, LIMIT)
  saveHistory(next)
  return next
}
