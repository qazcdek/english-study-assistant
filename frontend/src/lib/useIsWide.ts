import { useEffect, useState } from 'react'

/**
 * 표를 표로 그릴 만한 너비인가.
 *
 * **Tailwind 의 `sm` 과 같은 값이다.** 숫자가 두 곳에 있는 것은 피할 수 없다 —
 * CSS 쪽은 `sm:` 접두사로만 쓰고 JS 쪽은 값을 알아야 한다. 그러므로 **여기가 유일한
 * JS 쪽 원본**이고, 바꿀 때는 `sm` 을 함께 본다.
 */
export const WIDE = '(min-width: 640px)'

/**
 * CSS 로만 숨기지 않고 **한쪽만 그린다.**
 *
 * `sm:hidden` 과 `hidden sm:block` 으로 두 벌을 다 심으면, 화면에는 하나만 보이지만
 * DOM 에는 둘이 있다. 그러면 같은 글이 두 번 읽히고(스크린 리더), 검사도
 * "그 글자가 하나뿐인가" 를 물을 수 없게 된다. 분기를 JS 로 가져오면 DOM 에 하나만 남는다.
 *
 * `matchMedia` 가 없는 자리(jsdom)에서는 **넓은 쪽**으로 둔다. 좁은 쪽을 보려면
 * 검사가 일부러 좁게 만든다.
 *
 * 근거: 10-code-conventions.md §9.2
 */
export function useIsWide(): boolean {
  const [wide, setWide] = useState(() => window.matchMedia?.(WIDE).matches ?? true)

  useEffect(() => {
    const query = window.matchMedia?.(WIDE)
    if (!query) return
    const onChange = (e: MediaQueryListEvent) => setWide(e.matches)
    query.addEventListener('change', onChange)
    // 처음 읽은 값과 지금이 다를 수 있다 — 기기를 돌리거나 창을 끌어 늘린 경우.
    setWide(query.matches)
    return () => query.removeEventListener('change', onChange)
  }, [])

  return wide
}
