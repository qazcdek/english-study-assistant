import { Fragment, useState } from 'react'

import type { VocabularyStore } from '../lib/useVocabulary'
import type { Expression, ExpressionType, Level } from '../lib/types'
import { ConfirmDialog } from './ConfirmDialog'
import { FavoriteStar } from './FavoriteStar'
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

/** 제외하면 연습 기록이 사라진다는 경고. 서버의 연쇄 삭제와 같은 말을 해야 한다. */
export const REMOVE_WARNING =
  '나의 표현에서 제외하면 직접 써보기 기록이 사라집니다. 계속 진행하시겠습니까?'

interface Props {
  expressions: Expression[]
  keyExpressions?: string[]
  level: Level
  /** 이 표현들이 나온 원문. 나의 표현에 올릴 때 함께 저장한다. */
  sourceText: string
  vocab: VocabularyStore
}

export function ExpressionTable({
  expressions,
  keyExpressions = [],
  level,
  sourceText,
  vocab,
}: Props) {
  const highlighted = new Set(keyExpressions)
  // 답을 먼저 보면 인출 연습이 성립하지 않으므로 기본값은 가림이다.
  const [hideExamples, setHideExamples] = useState(true)
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  const [pending, setPending] = useState<string | null>(null)
  // 연습 기록이 딸린 표현을 제외할 때만 채워진다.
  const [confirming, setConfirming] = useState<{ id: number; expression: string } | null>(null)

  if (expressions.length === 0) {
    return <p className="text-sm text-stone-400">따로 짚을 만한 표현이 없습니다.</p>
  }

  const hasExample = expressions.some((e) => e.example)
  // 예문이 하나도 없으면 체크박스가 사라져 **연습 기능이 없는 것처럼 보인다.**
  // 실제로 배포본에서 그렇게 보였다 (H-019). 없으면 없다고 적는다.
  const practiceable = expressions.some(canPractice)
  // 연습할 수 있는 표현이 하나도 없으면 가려 둘 이유가 없다. 체크박스도 없으므로
  // 가린 채로 두면 예문을 **영영 못 보게 된다.**
  const masked = hideExamples && practiceable
  // 별 칸 + 표현 + 유형 + 의미 (+ 예문)
  const columnCount = hasExample ? 5 : 4

  async function toggle(e: Expression) {
    const expression = e.expression
    if (pending) return
    setPending(expression)
    try {
      if (!vocab.has(expression)) {
        await vocab.add(e, sourceText)
        return
      }
      const id = vocab.idOf(expression)
      if (id === null) return
      // 직접 써본 기록이 있으면 그것까지 사라지므로 한 번 더 묻는다.
      if (vocab.practiceCount(expression) > 0) {
        setConfirming({ id, expression })
        return
      }
      await vocab.remove(id)
    } finally {
      setPending(null)
    }
  }

  return (
    <div>
      <ConfirmDialog
        message={confirming ? REMOVE_WARNING : null}
        onCancel={() => setConfirming(null)}
        onConfirm={async () => {
          const target = confirming
          setConfirming(null)
          if (target) await vocab.remove(target.id)
        }}
      />

      {!hasExample && (
        <p className="mb-2 text-right text-xs text-stone-400">
          이번 분석에는 예문이 없어 <b className="font-medium">직접 써보기</b>를 할 수 없습니다
        </p>
      )}

      {hasExample && !practiceable && (
        <p className="mb-2 text-right text-xs text-stone-400">
          한국어 제시문이 없어 이번에는 <b className="font-medium">직접 써보기</b>를 할 수 없습니다
        </p>
      )}

      {hasExample && practiceable && (
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
              {/* 별 칸은 머리글을 비운다 — 아이콘 하나에 이름을 붙이면 표가 시끄러워진다. */}
              <th className="w-8 py-2" aria-label="나의 표현" />
              <th className="w-[24%] py-2 pr-3 font-medium">표현</th>
              <th className="w-[14%] py-2 pr-3 font-medium">유형</th>
              <th className="py-2 font-medium">의미 및 설명</th>
              {hasExample && (
                // 버튼만 들어갈 때는 유형 칸과 같은 폭이면 충분하다.
                // 예문을 펼쳐 보일 때만 넓게 쓴다.
                <th className={`py-2 pl-3 font-medium ${masked ? 'w-[14%]' : 'w-[22%]'}`}>
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
                    <td className="py-3">
                      <FavoriteStar
                        active={vocab.has(e.expression)}
                        busy={pending === e.expression}
                        onClick={() => void toggle(e)}
                      />
                    </td>
                    <td className="py-3 pr-3 font-mono font-medium text-stone-900 dark:text-stone-100">
                      {e.expression}
                      {highlighted.has(e.expression) && (
                        // 전에는 이 자리에 ★ 를 뒀는데, 왼쪽 별이 즐겨찾기를 뜻하게 되면서
                        // **같은 글자가 두 가지 뜻**이 됐다. 글자 라벨로 바꾼다.
                        <span
                          className="ml-1.5 whitespace-nowrap rounded bg-amber-100 px-1 py-px align-middle font-sans text-[10px] font-medium text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                          title="총평에서 꼽은 표현"
                        >
                          핵심
                        </span>
                      )}
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
                        ) : !masked ? (
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
                          sourceText={sourceText}
                          // 채점이 끝나면 서버가 이 표현을 나의 표현에 올려 두었다.
                          // 다시 읽어 와야 왼쪽 별이 노랗게 바뀐다.
                          onGraded={vocab.reload}
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
