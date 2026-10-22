import { useCallback, useEffect, useState } from 'react'

import { ApiError, listPracticeHistory } from '../lib/api'
import type {
  Expression,
  ExpressionType,
  Level,
  PracticeHistoryItem,
  VocabularyItem,
} from '../lib/types'
import type { VocabularyStore } from '../lib/useVocabulary'
import { ConfirmDialog } from './ConfirmDialog'
import { REMOVE_WARNING } from './ExpressionTable'
import { PracticeBox } from './PracticeBox'
import { PracticeFeedback, VerdictBadge } from './PracticeFeedback'

/**
 * 연월일 시분초. **날짜만으로는 부족하다** — 같은 표현을 한 날에 여러 번 쓰면
 * 어느 것이 나중 시도인지 구별되지 않는다.
 */
export function stamp(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  const date = `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`
  return `${date} ${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`
}

/**
 * 담아 둔 항목을 연습이 쓰는 모양으로 바꾼다.
 *
 * 나의 표현에서도 **분석 화면과 똑같은 연습**을 한다. 그러려면 같은 컴포넌트에
 * 같은 모양을 넘겨야 한다 — 비슷한 걸 하나 더 만들면 한쪽만 고쳐져 갈라진다.
 *
 * `type` 은 서버에서 자유 문자열로 온다(옛 기록이나 자동 등록 때 빌 수 있다).
 * 화면은 유형 목록 중 하나로 다루므로 여기서 한 번만 좁힌다.
 */
export function asExpression(item: VocabularyItem): Expression {
  return {
    expression: item.expression,
    type: (item.type || '고급 어휘') as ExpressionType,
    meaning: item.meaning,
    example: item.example,
    example_ko: item.example_ko,
  }
}

/** 예문과 한국어 제시문이 둘 다 있어야 연습할 수 있다 — 분석 화면과 같은 조건이다. */
function canPractice(item: VocabularyItem): boolean {
  return Boolean(item.example && item.example_ko)
}

/** 쓴 기록 한 건. 접힌 채로는 판정과 일시만, 펴면 AI 평가가 그대로 나온다. */
function Record({ row }: { row: PracticeHistoryItem }) {
  const [open, setOpen] = useState(false)

  return (
    <li className="flex flex-col gap-1.5 rounded-lg bg-white/70 p-3 dark:bg-stone-900/50">
      <div className="flex flex-wrap items-center gap-2">
        <VerdictBadge result={row.feedback} />
        <time className="ml-auto font-mono text-xs text-stone-400">{stamp(row.created_at)}</time>
      </div>

      <p className="font-mono text-sm leading-relaxed text-stone-900 dark:text-stone-100">
        {row.learner_answer}
      </p>

      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="self-start rounded-md text-xs text-stone-400 transition hover:text-stone-600 dark:hover:text-stone-300"
      >
        {open ? '접기 ▴' : '자세히 보기 ▾'}
      </button>

      {open && (
        <div className="border-t border-stone-200/70 pt-3 dark:border-stone-700/60">
          <p className="mb-3 border-l-2 border-stone-300 pl-2.5 text-xs leading-relaxed text-stone-500 dark:border-stone-600 dark:text-stone-400">
            {row.prompt_ko}
          </p>
          {/* 채점 직후와 같은 컴포넌트다. 그래서 "그때 본 평가 그대로" 가 보장된다. */}
          <PracticeFeedback
            result={row.feedback}
            learnerAnswer={row.learner_answer}
            modelAnswer={row.model_answer}
          />
        </div>
      )}
    </li>
  )
}

/** 한 표현의 쓴 기록 전부. 펼칠 때 가져온다 — 목록을 열 때 전부 가져오면 느리다. */
function History({ expression, reloadKey }: { expression: string; reloadKey: number }) {
  const [rows, setRows] = useState<PracticeHistoryItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setRows(null)
    listPracticeHistory(expression)
      .then((loaded) => alive && setRows(loaded))
      .catch(
        (e) => alive && setError(e instanceof ApiError ? e.message : '기록을 불러오지 못했습니다.'),
      )
    return () => {
      alive = false
    }
  }, [expression, reloadKey])

  if (error) return <p className="text-xs text-red-500">{error}</p>
  if (rows === null) return <p className="text-xs text-stone-400">불러오는 중…</p>
  if (rows.length === 0) {
    return <p className="text-xs text-stone-400">아직 직접 써본 기록이 없습니다.</p>
  }

  return (
    <ul className="flex flex-col gap-2">
      {rows.map((row) => (
        <Record key={row.id} row={row} />
      ))}
    </ul>
  )
}

function Row({
  item,
  level,
  onRemove,
  onPracticed,
}: {
  item: VocabularyItem
  level: Level
  onRemove: () => void
  onPracticed: () => void | Promise<void>
}) {
  const [showHistory, setShowHistory] = useState(false)
  const [practising, setPractising] = useState(false)
  // 연습을 한 번 더 하면 기록이 늘어난다. 펼쳐 둔 목록을 다시 읽게 한다.
  const [reloadKey, setReloadKey] = useState(0)

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
          </div>
          {item.meaning && (
            <p className="mt-1.5 text-sm leading-relaxed text-stone-600 dark:text-stone-300">
              {item.meaning}
            </p>
          )}
          {/* 예문은 접힌 채로 보여주지 않는다. 답을 먼저 보면 복습이 성립하지 않는다. */}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {canPractice(item) && (
            <button
              type="button"
              onClick={() => setPractising(!practising)}
              className={`whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs transition ${
                practising
                  ? 'border-indigo-300 bg-white text-indigo-700 dark:border-indigo-800 dark:bg-stone-900 dark:text-indigo-300'
                  : 'border-stone-200 text-stone-500 hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800'
              }`}
            >
              ✏ 직접 써보기
            </button>
          )}
          <button
            type="button"
            onClick={onRemove}
            title="나의 표현에서 제외"
            className="whitespace-nowrap rounded-lg border border-stone-200 px-2.5 py-1 text-xs text-stone-500 transition hover:border-red-300 hover:bg-red-50 hover:text-red-600 dark:border-stone-700 dark:hover:border-red-900 dark:hover:bg-red-950/40 dark:hover:text-red-400"
          >
            제외
          </button>
        </div>
      </div>

      {practising && (
        <div className="px-4 pb-4">
          <PracticeBox
            expression={asExpression(item)}
            level={level}
            sourceText={item.source_text}
            onGraded={async () => {
              setReloadKey((n) => n + 1)
              await onPracticed()
            }}
            onClose={() => setPractising(false)}
          />
        </div>
      )}

      <div className="border-t border-stone-100 px-4 py-2 dark:border-stone-800">
        <button
          type="button"
          onClick={() => setShowHistory(!showHistory)}
          className="flex w-full items-center gap-2 rounded-md py-1 text-xs text-stone-500 transition hover:text-stone-700 dark:hover:text-stone-300"
        >
          나의 기록 보기
          {item.practice_count > 0 && (
            <span className="rounded-full bg-stone-100 px-1.5 text-[11px] text-stone-500 dark:bg-stone-800 dark:text-stone-400">
              {item.practice_count}
            </span>
          )}
          <span className="ml-auto">{showHistory ? '▴' : '▾'}</span>
        </button>

        {showHistory && (
          <div className="pb-2 pt-1">
            <History expression={item.expression} reloadKey={reloadKey} />
          </div>
        )}
      </div>
    </li>
  )
}

/**
 * 나의 표현 목록.
 *
 * 들어오는 길은 둘이다 — 표현 풀이에서 별을 누르거나, **직접 써보기를 하면 자동으로**.
 * 자동 등록이 없으면 연습 기록에 닿을 화면이 없다 (`services/vocabulary.py`).
 *
 * 여기서도 **분석 화면과 똑같이** 연습한다. 복습이 목적이므로 담아 둔 뒤에 다시
 * 꺼내 쓸 수 있어야 하고, 그 연습 역시 기록으로 쌓인다.
 */
export function MyExpressions({ vocab, level }: { vocab: VocabularyStore; level: Level }) {
  const [confirming, setConfirming] = useState<VocabularyItem | null>(null)
  const [error, setError] = useState<string | null>(null)

  const remove = useCallback(
    async (item: VocabularyItem) => {
      try {
        await vocab.remove(item.id)
      } catch (e) {
        setError(e instanceof ApiError ? e.message : '제외하지 못했습니다.')
      }
    },
    [vocab],
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
              level={level}
              onPracticed={vocab.reload}
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
