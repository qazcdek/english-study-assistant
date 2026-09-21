import type { Level } from '../lib/types'

const STYLE: Record<Level, { label: string; title: string; className: string }> = {
  beginner: {
    label: '초',
    title: '초급',
    className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200',
  },
  intermediate: {
    label: '중',
    title: '중급',
    className: 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-200',
  },
  advanced: {
    label: '상',
    title: '상급',
    className: 'bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-200',
  },
}

/**
 * 분석 난이도 표시.
 *
 * 색만으로 구분하면 색각 이상이 있는 사람이 읽을 수 없어, 원 안에 글자를 함께 넣는다.
 */
export function LevelDot({ level }: { level?: Level }) {
  const style = level && STYLE[level]
  if (!style) {
    // 난이도를 저장하기 전에 쌓인 항목. 자리만 맞춰 목록이 들쭉날쭉해지지 않게 한다.
    return <span className="h-4 w-4 shrink-0" aria-hidden />
  }

  return (
    <span
      title={style.title}
      className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-medium leading-none ${style.className}`}
    >
      {style.label}
      <span className="sr-only">{style.title}</span>
    </span>
  )
}
