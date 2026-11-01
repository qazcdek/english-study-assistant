/**
 * 주소와 화면의 짝. **한 곳에만 둔다** — 흩어지면 주소와 화면이 어긋난다.
 *
 * **라우터를 들이지 않는다.** 화면이 넷이고 그중 하나만 매개변수를 받으므로
 * `history` API 로 충분하다 (07 §5.1 이 같은 오리진을 쓰는 덕이다).
 *
 * 주소가 필요한 이유는 셋이다 —
 * 1. **법적 문서 둘은 주소로 들어올 수 있어야 한다.** Google OAuth 심사가
 *    개인정보처리방침 URL 을 받고, 그것을 로그인 없이 열어 본다 (07 §10.2).
 * 2. **뒤로 가기.** 기록 하나를 열고 뒤로 누르면 목록으로 돌아가야 한다.
 *    전에는 주소가 `/` 하나였으므로 **앱 밖으로 나갔다** (H-038).
 * 3. **기록 하나를 링크할 수 있다.** 같은 주소로 다시 들어오면 그 기록이 열린다.
 *
 * `App.tsx` 가 이 짝을 들고 있었는데, 거기 두면 검사가 화면을 띄워야만 물을 수 있다.
 * 주소 해석은 순수한 판단이라 따로 둔다.
 */

/** 매개변수 없는 화면들. */
export const PATHS = {
  analyze: '/',
  mine: '/mine',
  terms: '/terms',
  privacy: '/privacy',
} as const

export type View = keyof typeof PATHS

/** 기록 하나를 보고 있을 때의 주소. **분석 화면의 매개변수**다 — 따로 선 화면이 아니다. */
const RECORD_PREFIX = '/analysis/'

export interface Route {
  view: View
  /** 분석 화면이 띄워 둔 기록. `null` 이면 방금 분석한 것이거나 빈 화면이다. */
  recordId: string | null
}

export function pathOf(route: Route): string {
  if (route.view === 'analyze' && route.recordId) return `${RECORD_PREFIX}${route.recordId}`
  return PATHS[route.view]
}

export function routeOf(pathname: string): Route {
  if (pathname.startsWith(RECORD_PREFIX)) {
    const id = pathname.slice(RECORD_PREFIX.length)
    // **기록 id 는 숫자다.** 아닌 것을 서버에 물으면 400 이 나고, 그 오류는
    // 사용자가 고칠 수 있는 것이 아니다. 모르는 주소는 분석 화면으로 둔다.
    if (/^[1-9][0-9]*$/.test(id)) return { view: 'analyze', recordId: id }
  }
  const found = (Object.keys(PATHS) as View[]).find((key) => PATHS[key] === pathname)
  return { view: found ?? 'analyze', recordId: null }
}
