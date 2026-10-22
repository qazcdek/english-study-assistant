import type { PracticeResult, Verdict } from '../lib/types'

export const VERDICT_STYLE: Record<Verdict, string> = {
  정확함: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  통함: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  다시: 'bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300',
}

export const VERDICT_MARK: Record<Verdict, string> = { 정확함: '✓', 통함: '△', 다시: '✗' }

/** 판정과 목표 표현 사용 여부. 기록 목록에서도 접힌 채로 이 줄만 보여준다. */
export function VerdictBadge({ result }: { result: PracticeResult }) {
  return (
    <>
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
    </>
  )
}

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
function Sentence({ label, text, accent }: { label: string; text: string; accent?: boolean }) {
  return (
    <div className="min-w-0 flex-1">
      <p className="mb-1 text-xs text-stone-400">{label}</p>
      <p
        className={`break-words rounded-lg px-3 py-2 font-mono text-sm leading-relaxed ${
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
  result: PracticeResult
  learnerAnswer: string
  modelAnswer: string
}

/**
 * AI 가 매긴 평가 한 건을 그린다.
 *
 * **채점 직후와 나중에 기록으로 되돌려 볼 때가 같은 모양이어야 한다.** 그래서 한
 * 컴포넌트에 모아 둔다 — 베껴 쓰면 한쪽만 고쳐져 갈라지고, 그때 "전에 본 평가와
 * 다르다" 는 의심이 생기면 기록 자체를 못 믿게 된다.
 *
 * 저장된 `practices.feedback` 이 `PracticeResult` 와 같은 모양이라 그대로 넘긴다.
 */
export function PracticeFeedback({ result, learnerAnswer, modelAnswer }: Props) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 sm:flex-row">
        <Sentence label="내 문장" text={learnerAnswer} accent />
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
                {result.other_notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            )}
          </Line>
        )}
      </div>
    </div>
  )
}
