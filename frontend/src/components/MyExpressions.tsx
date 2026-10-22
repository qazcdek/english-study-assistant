import { useCallback, useEffect, useState } from 'react'

import { ApiError, listPracticeHistory } from '../lib/api'
import type { PracticeHistoryItem, Verdict, VocabularyItem } from '../lib/types'
import type { VocabularyStore } from '../lib/useVocabulary'
import { ConfirmDialog } from './ConfirmDialog'
import { REMOVE_WARNING } from './ExpressionTable'

const VERDICT_STYLE: Record<Verdict, string> = {
  정확함: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  통함: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  다시: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300',
}

const VERDICT_MARK: Record<Verdict, string> = { 정확함: '✓', 통함: '△', 다시: '✗' }

function day(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ''
  return `${at.getMonth() + 1}월 ${at.getDate()}일`
}

/** 한 표현의 직접 써본 기록. 펼칠 때 가져온다 — 목록을 열 때 전부 가져오면 느리다. */
function PracticeHistory({ expression }: { expression: string }) {
  const [rows, setRows] = useState<PracticeHistoryItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    listPracticeHistory(expression)
      .then((loaded) => alive && setRows(loaded))
      .catch((e) => alive && setError(e instanceof ApiError ? e.message : '기록을 불러오지 못했습니다.'))
    return () => {
      alive = false
    }
  }, [expression])

  if (error) return <p className="px-4 py-3 text-xs text-red-500">{error}</p>
  if (rows === null) return <p className="px-4 py-3 text-xs text-stone-400">불러오는 중…</p>
  if (rows.length === 0) {
    return <p className="px-4 py-3 text-xs text-stone-400">아직 직접 써본 기록이 없습니다.</p>
  }

  return (
    <ul className="flex flex-col gap-3 px-4 py-3">
      {rows.map((row) => (
        <li key={row.id} className="flex flex-col gap-1.5 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${VERDICT_STYLE[row.verdict]}`}
            >
              {VERDICT_MARK[row.verdict]} {row.verdict}
            </span>
            <span
              className={`text-xs ${
                row.uses_target ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-500'
              }`}
            >
              목표 표현 {row.uses_target ? '사용함' : '쓰지 않음'}
            </span>
            <span className="ml-auto text-xs text-stone-400">{day(row.created_at)}</span>
          </div>
          <p className="border-l-2 border-stone-200 pl-2.5 text-xs leading-relaxed text-stone-500 dark:border-stone-700 dark:text-stone-400">
            {row.prompt_ko}
          </p>
          {/* 내가 쓴 문장을 먼저 둔다. 복습의 대상은 모범 답안이 아니라 내 문장이다. */}
          <p className="rounded-lg bg-white px-3 py-2 font-mono text-xs leading-relaxed text-stone-900 dark:bg-stone-900 dark:text-stone-100">
            {row.learner_answer}
          </p>
          <p className="px-3 font-mono text-xs leading-relaxed text-stone-400">
            모범 답안 · {row.model_answer}
          </p>
          {row.feedback.corrected && (
            <p className="px-3 text-xs leading-relaxed text-stone-500 dark:text-stone-400">
              고쳐 쓰면 · <span className="font-mono">{row.feedback.corrected}</span>
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}

function Row({
  item,
  open,
  onToggle,
  onRemove,
}: {
  item: VocabularyItem
  open: boolean
  onToggle: () => void
  onRemove: () => void
}) {
  return (
    <li className="rounded-xl border border-stone-200 dark:border-stone-800">
      <div className="flex flex-wrap items-start gap-2 p-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono font-medium text-stone-900 dark:text-stone-100">
              {item.expression}
            </span>
            {item.type && (
              <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500 dark:bg-stone-800 dark:text-stone-400">
                {item.type}
              </span>
            )}
            {item.practice_count > 0 && (
              <button
                type="button"
                onClick={onToggle}
                className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700 transition hover:bg-indigo-200 dark:bg-indigo-950 dark:text-indigo-300 dark:hover:bg-indigo-900"
              >
                직접 써보기 {item.practice_count}회 {open ? '▴' : '▾'}
              </button>
            )}
          </div>
          {item.meaning && (
            <p className="mt-1.5 text-sm leading-relaxed text-stone-600 dark:text-stone-300">
              {item.meaning}
            </p>
          )}
          {item.example && (
            <p className="mt-1 font-mono text-xs italic leading-relaxed text-stone-400">
              “{item.example}”
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onRemove}
          title="나의 표현에서 제외"
          className="shrink-0 rounded-lg border border-stone-200 px-2.5 py-1 text-xs text-stone-500 transition hover:border-red-300 hover:bg-red-50 hover:text-red-600 dark:border-stone-700 dark:hover:border-red-900 dark:hover:bg-red-950/40 dark:hover:text-red-400"
        >
          제외
        </button>
      </div>

      {open && (
        <div className="border-t border-stone-100 bg-stone-50/60 dark:border-stone-800 dark:bg-stone-900/40">
          <PracticeHistory expression={item.expression} />
        </div>
      )}
    </li>
  )
}

/**
 * 나의 표현 목록.
 *
 * 들어오는 길은 둘이다 — 표현 풀이에서 별을 누르거나, **직접 써보기를 하면 자동으로**.
 * 자동 등록이 없으면 연습 기록에 닿을 화면이 없다 (`services/vocabulary.py`).
 */
export function MyExpressions({ vocab }: { vocab: VocabularyStore }) {
  const [openId, setOpenId] = useState<number | null>(null)
  const [confirming, setConfirming] = useState<VocabularyItem | null>(null)
  const [error, setError] = useState<string | null>(null)

  const remove = useCallback(
    async (item: VocabularyItem) => {
      try {
        await vocab.remove(item.id)
        if (openId === item.id) setOpenId(null)
      } catch (e) {
        setError(e instanceof ApiError ? e.message : '제외하지 못했습니다.')
      }
    },
    [vocab, openId],
  )

  return (
    <div className="flex flex-col gap-4">
      <ConfirmDialog
        message={confirming ? REMOVE_WARNING : null}
        onCancel={() => setConfirming(null)}
        onConfirm={async () => {
          const target = confirming
          setConfirming(null)
          if (target) await remove(target)
        }}
      />

      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold tracking-tight">나의 표현</h2>
        <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500 dark:bg-stone-800">
          {vocab.items.length}
        </span>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {vocab.items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-stone-300 p-10 text-center text-sm leading-relaxed text-stone-400 dark:border-stone-700">
          아직 담아 둔 표현이 없습니다.
          <br />
          표현 풀이 왼쪽의 <span className="text-amber-500">☆</span> 를 누르거나,{' '}
          <b className="font-medium">직접 써보기</b>를 하면 여기에 모입니다.
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {vocab.items.map((item) => (
            <Row
              key={item.id}
              item={item}
              open={openId === item.id}
              onToggle={() => setOpenId(openId === item.id ? null : item.id)}
              // 직접 써본 기록이 있으면 그것까지 사라지므로 한 번 더 묻는다.
              onRemove={() =>
                item.practice_count > 0 ? setConfirming(item) : void remove(item)
              }
            />
          ))}
        </ul>
      )}
    </div>
  )
}
