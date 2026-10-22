interface Props {
  /** 나의 표현에 들어 있나. 노란 별과 빈 별을 가른다. */
  active: boolean
  busy?: boolean
  onClick: () => void
}

/**
 * 나의 표현에 넣고 빼는 별.
 *
 * 채운 별과 빈 별을 **같은 글자로** 그리지 않는다 — `★` 의 색만 바꾸면 회색 별이
 * "꺼진 상태"인지 "비활성"인지 구별되지 않는다. 테두리만 있는 `☆` 는 누를 수 있는
 * 빈 칸으로 읽힌다.
 */
export function FavoriteStar({ active, busy = false, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      aria-pressed={active}
      aria-label={active ? '나의 표현에서 제외' : '나의 표현에 추가'}
      title={active ? '나의 표현에서 제외' : '나의 표현에 추가'}
      className={`-ml-1 rounded-md px-1 text-base leading-none transition disabled:opacity-40 ${
        active
          ? 'text-amber-500 hover:text-amber-600'
          : 'text-stone-300 hover:text-amber-400 dark:text-stone-600'
      }`}
    >
      {active ? '★' : '☆'}
    </button>
  )
}
