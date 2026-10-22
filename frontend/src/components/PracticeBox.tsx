import { useState } from 'react'

import { ApiError, gradePractice } from '../lib/api'
import type { Expression, Level, PracticeResult } from '../lib/types'
import { PracticeFeedback, VerdictBadge } from './PracticeFeedback'

interface Props {
  expression: Expression
  level: Level
  /** 이 표현이 나온 원문. 채점과 함께 나의 표현에 올라간다. */
  sourceText: string
  /** 채점이 끝난 뒤. 서버가 이 표현을 나의 표현에 올려 두었으므로 목록을 다시 읽는다. */
  onGraded: () => void | Promise<void>
  onClose: () => void
}

export function PracticeBox({ expression, level, sourceText, onGraded, onClose }: Props) {
  const [answer, setAnswer] = useState('')
  const [grading, setGrading] = useState(false)
  const [result, setResult] = useState<PracticeResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const promptKo = expression.example_ko ?? ''
  const modelAnswer = expression.example ?? ''
  const canSubmit = answer.trim().length > 0 && !grading

  async function submit() {
    if (!canSubmit) return
    setGrading(true)
    setError(null)
    try {
      const response = await gradePractice({
        expression: expression.expression,
        meaning: expression.meaning,
        prompt_ko: promptKo,
        model_answer: modelAnswer,
        learner_answer: answer.trim(),
        level,
        // 채점은 이 둘을 안 쓴다. 서버가 같은 트랜잭션에서 나의 표현에 올릴 때 쓴다.
        type: expression.type,
        source_text: sourceText,
      })
      setResult(response.result)
      // 직접 써본 표현은 자동으로 나의 표현에 올라간다. 별이 그걸 반영해야 한다.
      await onGraded()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '채점에 실패했습니다.')
    } finally {
      setGrading(false)
    }
  }

  return (
    <div className="rounded-xl border border-indigo-200 bg-white/70 p-4 dark:border-indigo-900/60 dark:bg-stone-900/40">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
          작문 연습
        </span>
        <span className="text-xs text-stone-500 dark:text-stone-400">
          <b className="font-mono text-stone-800 dark:text-stone-200">{expression.expression}</b>
          {' 을(를) 써서 아래 뜻이 되도록 영작해 보세요'}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="ml-auto rounded-md px-2 py-1 text-xs text-stone-400 transition hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-200"
        >
          닫기
        </button>
      </div>

      <p className="mb-3 border-l-2 border-indigo-300 pl-3 text-[15px] leading-relaxed text-stone-800 dark:border-indigo-800 dark:text-stone-100">
        {promptKo}
      </p>

      {!result ? (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                e.preventDefault()
                void submit()
              }
            }}
            rows={2}
            autoFocus
            spellCheck={false}
            placeholder="영어로 써 보세요"
            className="w-full flex-1 resize-y rounded-lg border border-stone-200 bg-white p-2.5 font-mono text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-stone-700 dark:bg-stone-950 dark:focus:ring-indigo-900"
          />
          <div className="flex shrink-0 items-center gap-2">
            {error && <span className="text-xs text-red-500">{error}</span>}
            <button
              type="button"
              onClick={submit}
              disabled={!canSubmit}
              className="ml-auto whitespace-nowrap rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:bg-stone-300 dark:disabled:bg-stone-700"
            >
              {grading ? '채점 중…' : '채점하기'}
            </button>
            <kbd className="hidden whitespace-nowrap text-xs text-stone-400 lg:inline">
              ⌘/Ctrl + ↵
            </kbd>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <VerdictBadge result={result} />
            <button
              type="button"
              onClick={() => {
                setResult(null)
                setError(null)
              }}
              className="ml-auto rounded-lg border border-stone-200 px-2.5 py-1 text-xs transition hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
            >
              다시 써보기
            </button>
          </div>

          <PracticeFeedback
            result={result}
            learnerAnswer={answer.trim()}
            modelAnswer={modelAnswer}
          />
        </div>
      )}
    </div>
  )
}
