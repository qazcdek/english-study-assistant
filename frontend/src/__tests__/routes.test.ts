import { describe, expect, test } from 'vitest'

import { PATHS, pathOf, routeOf, tabsFor } from '../lib/routes'

describe('주소와 화면은 서로 되돌아간다', () => {
  test('매개변수 없는 화면들', () => {
    for (const view of Object.keys(PATHS) as (keyof typeof PATHS)[]) {
      const path = PATHS[view]
      expect(pathOf({ view, recordId: null })).toBe(path)
      expect(routeOf(path)).toEqual({ view, recordId: null })
    }
  })

  test('기록 하나는 분석 화면의 매개변수다', () => {
    expect(pathOf({ view: 'analyze', recordId: '12' })).toBe('/analysis/12')
    expect(routeOf('/analysis/12')).toEqual({ view: 'analyze', recordId: '12' })
  })

  test('기록 id 는 다른 화면으로 새지 않는다', () => {
    // 나의 표현을 보던 중에는 기록이 주소에 없다 — 분석 화면의 것이기 때문이다.
    expect(pathOf({ view: 'mine', recordId: '12' })).toBe('/mine')
  })

  test('숫자가 아닌 기록 주소는 분석 화면으로 둔다', () => {
    // 서버에 물으면 400 이고, 그 오류는 사용자가 고칠 수 있는 것이 아니다.
    for (const bad of ['/analysis/', '/analysis/abc', '/analysis/0', '/analysis/1/2']) {
      expect(routeOf(bad)).toEqual({ view: 'analyze', recordId: null })
    }
  })

  test('모르는 주소는 분석 화면이다', () => {
    expect(routeOf('/nope')).toEqual({ view: 'analyze', recordId: null })
  })
})

describe('머리의 탭', () => {
  test('글감은 cloud 에만 있다', () => {
    // 공용 글감은 cloud 전용이다 (09 §3.8). local 은 표가 늘 비어 있으므로
    // 아무것도 없는 화면으로 가는 문을 달지 않는다.
    expect(tabsFor(true).map(([view]) => view)).toContain('article')
    expect(tabsFor(false).map(([view]) => view)).not.toContain('article')
  })

  test('분석과 나의 표현은 두 모드에 다 있다', () => {
    for (const cloud of [true, false]) {
      const views = tabsFor(cloud).map(([view]) => view)
      expect(views).toContain('analyze')
      expect(views).toContain('mine')
    }
  })

  test('탭마다 갈 주소가 있다', () => {
    // 주소 없는 탭을 누르면 `pathOf` 가 undefined 를 밀어 넣어 주소가 깨진다.
    for (const [view] of tabsFor(true)) {
      expect(PATHS[view]).toBeTruthy()
    }
  })
})
