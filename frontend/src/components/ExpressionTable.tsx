import { Fragment, useState } from 'react'

import type { Expression, ExpressionType, Level } from '../lib/types'
import { PracticeBox } from './PracticeBox'

const TYPE_COLORS: Record<ExpressionType, string> = {
  '고급 어휘': 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300',
  관용구: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  'Phrasal Verb': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
  '연어(Collocation)': 'bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300',
  '문법 포인트': 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300',
  '구어 표현': 'bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-950 dark:text-fuchsia-300',
  '전문 용어': 'bg-stone-200 text-stone-700 dark:bg-stone-800 dark:text-stone-300',
}

const FALLBACK = 'bg-stone-200 text-stone-700 dark:bg-stone-800 dark:text-stone-300'

/** 예문과 그 한국어 뜻이 둘 다 있어야 작문 연습을 할 수 있다. */
function canPractice(e: Expression): boolean {
  return Boolean(e.example && e.example_ko)
}

interface Props {
  expressions: Expression[]
  keyExpressions?: string[]
  level: Level
}

export function ExpressionTable({ expressions, keyExpressions = [], level }: Props) {
  const highlighted = new Set(keyExpressions)
  // 답을 먼저 보면 인출 연습이 성립하지 않으므로 기본값은 가림이다.
  const [hideExamples, setHideExamples] = useState(true)
  const [openIndex, setOpenIndex] = useState<number | null>(null)

  if (expressions.length === 0) {
    return <p className="text-sm text-stone-400">따로 짚을 만한 표현이 없습니다.</p>
  }

  const hasExample = expressions.some((e) => e.example)
  const columnCount = hasExample ? 4 : 3

  return (
    <div>
      {hasExample && (
        <label className="mb-2 flex cursor-pointer items-center justify-end gap-1.5 text-xs text-stone-400">
          <input
            type="checkbox"
            checked={hideExamples}
            onChange={(e) => {
              setHideExamples(e.target.checked)
              setOpenIndex(null)
            }}
            className="accent-indigo-600"
          />
          예문 가리고 직접 써보기
        </label>
      )}

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-stone-200 text-left text-xs uppercase tracking-wide text-stone-400 dark:border-stone-800">
              <th className="w-[26%] py-2 pr-3 font-medium">표현</th>
              <th className="w-[14%] py-2 pr-3 font-medium">유형</th>
              <th className="py-2 font-medium">의미 및 설명</th>
              {hasExample && (
                // 버튼만 들어갈 때는 유형 칸과 같은 폭이면 충분하다.
                // 예문을 펼쳐 보일 때만 넓게 쓴다.
                <th className={`py-2 pl-3 font-medium ${hideExamples ? 'w-[14%]' : 'w-[22%]'}`}>
                  예문
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {expressions.map((e, i) => {
              const open = openIndex === i
              return (
                <Fragment key={`${e.expression}-${i}`}>
                  <tr
                    className={`align-top ${
                      open
                        ? 'bg-indigo-50/40 dark:bg-indigo-950/20'
                        : 'border-b border-stone-100 last:border-0 dark:border-stone-800/60'
                    }`}
                  >
                    <td className="py-3 pr-3 font-mono font-medium text-stone-900 dark:text-stone-100">
                      {highlighted.has(e.expression) && (
                        <span className="mr-1 text-amber-500" title="총평에서 꼽은 표현">
                          ★
                        </span>
                      )}
                      {e.expression}
                    </td>
                    <td className="py-3 pr-3">
                      <span
                        className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs ${
                          TYPE_COLORS[e.type] ?? FALLBACK
                        }`}
                      >
                        {e.type}
                      </span>
                    </td>
                    <td className="py-3 leading-relaxed text-stone-700 dark:text-stone-300">
                      {e.meaning}
                      {e.nuance && (
                        // 초급에서는 이 줄이 아예 없다.
                        <p className="mt-1 text-xs leading-relaxed text-stone-500 dark:text-stone-400">
                          {e.nuance}
                        </p>
                      )}
                    </td>
                    {hasExample && (
                      <td className="py-3 pl-3">
                        {!e.example ? (
                          <span className="text-xs text-stone-300 dark:text-stone-600">—</span>
                        ) : !hideExamples ? (
                          <p className="font-mono text-xs italic text-stone-400">“{e.example}”</p>
                        ) : canPractice(e) ? (
                          <button
                            type="button"
                            onClick={() => setOpenIndex(open ? null : i)}
                            className={`whitespace-nowrap rounded-lg border px-2 py-1 text-xs transition ${
                              open
                                ? 'border-indigo-300 bg-white text-indigo-700 dark:border-indigo-800 dark:bg-stone-900 dark:text-indigo-300'
                                : 'border-stone-200 text-stone-500 hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800'
                            }`}
                          >
                            ✏ 직접 써보기
                          </button>
                        ) : (
                          <span
                            className="text-xs text-stone-300 dark:text-stone-600"
                            title="한국어 제시문이 없어 연습할 수 없습니다"
                          >
                            가려짐
                          </span>
                        )}
                      </td>
                    )}
                  </tr>

                  {open && (
                    <tr className="border-b border-stone-100 last:border-0 dark:border-stone-800/60">
                      {/* 퀴즈는 그 표현 하나에 대한 것이므로 표 전체 폭을 쓴다. */}
                      <td colSpan={columnCount} className="bg-indigo-50/40 pb-4 dark:bg-indigo-950/20">
                        <PracticeBox
                          expression={e}
                          level={level}
                          onClose={() => setOpenIndex(null)}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
