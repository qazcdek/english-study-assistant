import { useState } from 'react'

import { ApiError, gradePractice } from '../lib/api'
import type { Expression, Level, PracticeResult, Verdict } from '../lib/types'

const VERDICT_STYLE: Record<Verdict, string> = {
  정확함: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  통함: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  다시: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300',
}

const VERDICT_MARK: Record<Verdict, string> = { 정확함: '✓', 통함: '△', 다시: '✗' }

/** 라벨을 왼쪽에 고정폭으로 두고 본문을 흘린다. 항목 간 시선이 맞는다. */
function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 text-sm leading-relaxed">
      <span className="w-[4.5rem] shrink-0 pt-px text-xs text-stone-400">{label}</span>
      <span className="min-w-0 flex-1 text-stone-700 dark:text-stone-300">{children}</span>
    </div>
  )
}

/** 내 문장과 모범 답안을 나란히 둬서 차이가 바로 보이게 한다. */
function Sentence({
  label,
  text,
  accent,
}: {
  label: string
  text: string
  accent?: boolean
}) {
  return (
    <div className="min-w-0 flex-1">
      <p className="mb-1 text-xs text-stone-400">{label}</p>
      <p
        className={`rounded-lg px-3 py-2 font-mono text-sm leading-relaxed ${
          accent
            ? 'bg-white text-stone-900 dark:bg-stone-900 dark:text-stone-100'
            : 'bg-white/60 text-stone-500 dark:bg-stone-900/60 dark:text-stone-400'
        }`}
      >
        {text}
      </p>
    </div>
  )
}

interface Props {
  expression: Expression
  level: Level
  onClose: () => void
}

export function PracticeBox({ expression, level, onClose }: Props) {
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
      })
      setResult(response.result)
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
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${VERDICT_STYLE[result.verdict]}`}
            >
              {VERDICT_MARK[result.verdict]} {result.verdict}
            </span>
            <span
              className={`text-xs ${
                result.uses_target ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-500'
              }`}
            >
              목표 표현 {result.uses_target ? '사용함' : '쓰지 않음'}
            </span>
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

          <div className="flex flex-col gap-3 sm:flex-row">
            <Sentence label="내 문장" text={answer.trim()} accent />
            <Sentence label="모범 답안" text={modelAnswer} />
          </div>

          <div className="flex flex-col gap-1.5 border-t border-stone-200/70 pt-3 dark:border-stone-700/60">
            <Line label="잘한 점">{result.good_point}</Line>
            <Line label="목표 표현">{result.target_note}</Line>
            {result.corrected && (
              <Line label="고쳐 쓰면">
                <span className="font-mono">{result.corrected}</span>
              </Line>
            )}
            {result.other_notes.length > 0 && (
              <Line label="그 밖에">
                {result.other_notes.length === 1 ? (
                  result.other_notes[0]
                ) : (
                  <ul className="list-inside list-disc">
                    {result.other_notes.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                )}
              </Line>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
