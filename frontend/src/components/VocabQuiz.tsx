import { useCallback, useState } from 'react'

import { QUESTIONS, buildQuiz, shortBy, type Question } from '../lib/quiz'
import type { VocabularyItem } from '../lib/types'

/**
 * 나의 표현 4지 선다 퀴즈 (M2-T8).
 *
 * ### 서버를 타지 않는다
 *
 * 담아 둔 표현이 이미 화면에 있고 오답지도 그 안에서 고른다. **API 도 LLM 도 부르지
 * 않는다** — 기록을 저장하지 않기로 한 결정이 그걸 가능하게 한다.
 *
 * ### 문제를 한 번에 다 만들어 둔다
 *
 * 문제마다 새로 뽑으면 **같은 표현이 두 번 나올 수 있다.** 시작할 때 한 판을 만들고
 * 그 안에서만 넘긴다. 그래서 "새 퀴즈 시작" 은 판을 다시 만드는 일이다.
 *
 * ### 고른 뒤에는 바꿀 수 없다
 *
 * 답을 보고 다시 고르면 맞춘 것이 아니다. 고르면 정답을 보여주고 **다음** 으로만
 * 간다 — 인출 연습의 전제다 (`06 §1`).
 */
export function VocabQuiz({ items }: { items: VocabularyItem[] }) {
  const [quiz, setQuiz] = useState<Question[] | null>(null)
  const [at, setAt] = useState(0)
  const [picked, setPicked] = useState<string | null>(null)
  const [correct, setCorrect] = useState(0)

  const start = useCallback(() => {
    setQuiz(buildQuiz(items))
    setAt(0)
    setPicked(null)
    setCorrect(0)
  }, [items])

  const stop = useCallback(() => {
    setQuiz(null)
    setPicked(null)
  }, [])

  const short = shortBy(items)

  if (short > 0) {
    return (
      <div className="rounded-2xl border border-dashed border-stone-300 p-10 text-center text-sm leading-relaxed text-stone-400 dark:border-stone-700">
        담아 둔 표현의 <b className="font-medium">뜻이 겹쳐</b> 오답지를 채울 수
        없습니다.
        <br />
        뜻이 서로 다른 표현이 {short}개 더 필요합니다.
      </div>
    )
  }

  if (quiz === null) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl border border-stone-200 p-10 text-center dark:border-stone-800">
        <p className="text-sm text-stone-500 dark:text-stone-400">
          담아 둔 표현에서 <b className="font-medium">{QUESTIONS}문제</b>를 뽑아 뜻을
          맞춥니다. 기록은 남기지 않습니다.
        </p>
        <button
          type="button"
          onClick={start}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500"
        >
          퀴즈 시작
        </button>
      </div>
    )
  }

  const done = at >= quiz.length

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-stone-400">
        <span>
          {done ? `${quiz.length}문제 끝` : `${at + 1} / ${quiz.length}`} · 맞춘 것{' '}
          <b className="font-medium text-stone-600 dark:text-stone-300">{correct}</b>
        </span>
        <span className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={start}
            className="rounded-md px-2 py-1 transition hover:bg-stone-100 hover:text-stone-700 dark:hover:bg-stone-800 dark:hover:text-stone-200"
          >
            새 퀴즈 시작
          </button>
          <button
            type="button"
            onClick={stop}
            className="rounded-md px-2 py-1 transition hover:bg-stone-100 hover:text-stone-700 dark:hover:bg-stone-800 dark:hover:text-stone-200"
          >
            퀴즈 그만두기
          </button>
        </span>
      </div>

      {done ? (
        <div className="rounded-2xl border border-stone-200 p-10 text-center dark:border-stone-800">
          <p className="text-sm text-stone-600 dark:text-stone-300">
            {quiz.length}문제 중 <b className="font-medium">{correct}개</b> 맞췄습니다.
          </p>
        </div>
      ) : (
        <Card
          question={quiz[at]}
          picked={picked}
          onPick={(choice) => {
            if (picked !== null) return // **고른 뒤에는 바꿀 수 없다.**
            setPicked(choice)
            if (choice === quiz[at].answer) setCorrect((n) => n + 1)
          }}
          onNext={() => {
            setPicked(null)
            setAt((n) => n + 1)
          }}
        />
      )}
    </div>
  )
}

/** 문제 하나. 고르기 전에는 보기만, 고른 뒤에는 정·오답을 보여준다. */
function Card({
  question,
  picked,
  onPick,
  onNext,
}: {
  question: Question
  picked: string | null
  onPick: (choice: string) => void
  onNext: () => void
}) {
  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-stone-200 p-5 dark:border-stone-800">
      <p className="text-center font-mono text-lg font-medium text-stone-900 dark:text-stone-100">
        {question.expression}
      </p>

      <ul className="flex flex-col gap-2">
        {question.choices.map((choice) => (
          <li key={choice}>
            <button
              type="button"
              onClick={() => onPick(choice)}
              disabled={picked !== null}
              className={`w-full rounded-xl border px-4 py-3 text-left text-sm transition ${tone(choice, question.answer, picked)}`}
            >
              {choice}
            </button>
          </li>
        ))}
      </ul>

      {picked !== null && (
        <div className="flex items-center gap-3">
          <p className="text-sm">
            {picked === question.answer ? (
              <span className="font-medium text-emerald-600 dark:text-emerald-400">맞았습니다</span>
            ) : (
              <span className="text-stone-500 dark:text-stone-400">
                <b className="font-medium text-red-600 dark:text-red-400">틀렸습니다</b> — 정답은{' '}
                <b className="font-medium">{question.answer}</b>
              </span>
            )}
          </p>
          <button
            type="button"
            onClick={onNext}
            className="ml-auto rounded-lg bg-stone-800 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-stone-700 dark:bg-stone-200 dark:text-stone-900 dark:hover:bg-white"
          >
            다음
          </button>
        </div>
      )}
    </div>
  )
}

/** 보기 하나의 색. **고르기 전에는 아무것도 알려주지 않는다.** */
function tone(choice: string, answer: string, picked: string | null): string {
  if (picked === null) {
    return 'border-stone-200 hover:border-indigo-400 hover:bg-indigo-50/50 dark:border-stone-700 dark:hover:border-indigo-600 dark:hover:bg-indigo-950/30'
  }
  if (choice === answer) {
    return 'border-emerald-400 bg-emerald-50 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200'
  }
  if (choice === picked) {
    return 'border-red-300 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300'
  }
  return 'border-stone-200 text-stone-400 dark:border-stone-800 dark:text-stone-600'
}
