import type { ReactNode } from 'react'

import { OPERATOR, unfilled } from './operator'

/** 법적 문서 두 장이 공유하는 틀. 제목·시행일·돌아가기가 같은 자리에 있어야 한다. */
export function Legal({
  title,
  onBack,
  children,
}: {
  title: string
  onBack: () => void
  children: ReactNode
}) {
  const missing = unfilled()

  return (
    <article className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        <span className="text-xs text-stone-400">시행일 {OPERATOR.시행일}</span>
        <button
          type="button"
          onClick={onBack}
          className="ml-auto rounded-lg border border-stone-200 px-2.5 py-1 text-xs transition hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
        >
          돌아가기
        </button>
      </div>

      {missing.length > 0 && (
        // 배포 전에만 보인다. 검사가 이 상태를 막으므로 사용자는 볼 수 없다.
        <p className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          아직 채워지지 않은 항목이 있습니다 — {missing.join(' · ')}.
          이 상태로는 배포되지 않습니다.
        </p>
      )}

      <div className="flex flex-col gap-5 text-sm leading-relaxed text-stone-700 dark:text-stone-300">
        {children}
      </div>
    </article>
  )
}

/** 번호 붙은 조항. 두 문서가 같은 모양이어야 읽는 사람이 한 번만 익힌다. */
export function Clause({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">
        제{n}조 · {title}
      </h3>
      {children}
    </section>
  )
}

export function Items({ items }: { items: ReactNode[] }) {
  return (
    <ul className="flex list-outside list-disc flex-col gap-1.5 pl-5">
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  )
}
