import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, test } from 'vitest'

/**
 * 가로 스크롤을 만드는 꼴을 글자로 잡는다.
 *
 * **레이아웃은 jsdom 이 못 본다.** 그래서 "폭이 넘쳤는지" 는 검사할 수 없다.
 * 대신 **넘치게 만드는 두 가지 꼴**은 글자로 잡을 수 있다 —
 *
 * 1. `truncate` 를 `min-w-0` 없이 쓰는 것. flex·grid 자식의 기본 `min-width` 가
 *    `auto` 라서, 잘리지 않고 **내용 너비만큼 늘어난다.** 실제로 `HistoryList` 가
 *    그래서 가장 긴 원문만큼 넓어지고 페이지를 밀어냈다 (H-028).
 * 2. 뷰포트보다 큰 고정 폭(`w-[800px]` 같은 것).
 *
 * 이게 전부를 막지는 못한다. 10 §9.3 의 경계 그대로다 — 픽셀은 사람이 본다.
 */
// `import.meta.url` 은 vite 가 변환해 `/src/...` 로 남는다. 디스크 경로가 필요하다.
const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path)
    return /\.tsx?$/.test(entry.name) ? [path] : []
  })
}

/** `className="…"` 와 `className={`…`}` 안의 클래스 묶음들. */
function classLists(code: string): string[] {
  return [...code.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\})/g)].map(
    (m) => m[1] ?? m[2] ?? '',
  )
}

const FILES = sources(SRC)

test('훑을 파일을 실제로 찾았다', () => {
  expect(FILES.length).toBeGreaterThan(10)
})

describe('가로 스크롤을 만드는 꼴', () => {
  test('truncate 는 min-w-0 과 함께 쓴다', () => {
    const bad: string[] = []
    for (const path of FILES) {
      for (const list of classLists(readFileSync(path, 'utf8'))) {
        if (!/\btruncate\b/.test(list)) continue
        // `max-w-…` 로 폭을 묶어 둔 경우는 늘어나지 않으므로 괜찮다.
        //
        // **부모가 flex 인지 따져 예외를 두지 않는다.** 블록 요소면 `min-w-0` 없이도
        // 잘리지만, 부모를 보고 판단하는 추론이 바로 `HistoryList` 에서 틀린 자리다.
        // 규칙을 단순하게 두고 해롭지 않은 클래스 하나를 더 붙이는 쪽이 싸다.
        if (/\bmin-w-0\b/.test(list) || /\bmax-w-/.test(list)) continue
        bad.push(`${path.replace(SRC, 'src')} :: ${list.slice(0, 70)}`)
      }
    }
    expect(bad, '잘리지 않고 내용 너비만큼 늘어난다').toEqual([])
  })

  test('뷰포트보다 큰 고정 폭을 쓰지 않는다', () => {
    const bad: string[] = []
    for (const path of FILES) {
      for (const list of classLists(readFileSync(path, 'utf8'))) {
        for (const m of list.matchAll(/\b(?:min-)?w-\[(\d+)px\]/g)) {
          if (Number(m[1]) > 320) bad.push(`${path.replace(SRC, 'src')} :: ${m[0]}`)
        }
      }
    }
    expect(bad, '좁은 기기에서 폭을 넘긴다').toEqual([])
  })
})
