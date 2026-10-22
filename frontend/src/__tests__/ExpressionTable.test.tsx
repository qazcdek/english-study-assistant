import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test } from 'vitest'

import { ExpressionTable, REMOVE_WARNING } from '../components/ExpressionTable'
import { EXPRESSIONS, SOURCE, fakeStore, item, setViewport } from './fixtures'

function draw(store = fakeStore(), keyExpressions: string[] = []) {
  render(
    <ExpressionTable
      expressions={EXPRESSIONS}
      keyExpressions={keyExpressions}
      level="intermediate"
      sourceText={SOURCE}
      vocab={store}
    />,
  )
  return store
}

/**
 * 표현 한 줄의 별 버튼.
 *
 * **배치를 묻지 않는다** — 넓은 화면은 `tr`, 좁은 화면은 `li` 다. 한쪽 선택자로
 * 적으면 검사가 배치에 매달리게 되고, 그러면 두 배치를 같은 눈으로 볼 수 없다.
 */
function star(expression: string) {
  const row = screen.getByText(expression).closest('tr, li')
  if (!row) throw new Error(`${expression} 줄을 못 찾았다`)
  const button = row.querySelector('button[aria-pressed]')
  if (!button) throw new Error(`${expression} 줄에 별이 없다`)
  return button as HTMLButtonElement
}

/** 연습 버튼. `예문 가리고 직접 써보기` 체크박스 라벨과 글자가 겹치므로 역할로 찾는다. */
function practiceButtons() {
  return screen.getAllByRole('button', { name: /직접 써보기/ })
}

/**
 * 넓은 화면은 표, 좁은 화면은 카드로 그린다. **배치만 갈리고 내용은 한 벌이어야 한다.**
 * 그래서 아래 묶음은 두 너비에서 모두 돈다 — 한쪽만 고쳐져 갈라지는 것이 이 변경의
 * 가장 큰 위험이다.
 */
describe.each(['wide', 'narrow'] as const)('%s 에서', (kind) => {
  beforeEach(() => setViewport(kind))

  test('표현과 의미가 보인다', () => {
    draw()

    for (const e of EXPRESSIONS) {
      expect(screen.getByText(e.expression)).toBeTruthy()
      expect(screen.getByText(e.meaning)).toBeTruthy()
    }
  })

  test('유형 배지가 보인다', () => {
    draw()

    expect(screen.getByText('고급 어휘')).toBeTruthy()
    expect(screen.getByText('Phrasal Verb')).toBeTruthy()
  })

  test('담아 두지 않은 표현은 빈 별, 담아 둔 것은 채운 별', () => {
    draw(fakeStore([item({ expression: 'refer to' })]))

    expect(star('refer to').textContent).toBe('★')
    expect(star('enlist').textContent).toBe('☆')
  })

  test('빈 별을 누르면 담긴다', () => {
    const store = draw()
    fireEvent.click(star('enlist'))

    expect(store.added).toEqual(['enlist'])
  })

  test('쓴 기록이 있는 표현을 제외할 때는 한 번 더 묻는다', () => {
    const store = draw(fakeStore([item({ id: 7, practice_count: 2 })]))
    fireEvent.click(star('refer to'))

    expect(screen.getByText(REMOVE_WARNING)).toBeTruthy()
    expect(store.removed).toEqual([])
  })

  test('총평이 꼽은 표현은 핵심 배지를 단다', () => {
    draw(fakeStore(), ['enlist'])

    expect(screen.getByText('핵심')).toBeTruthy()
  })

  test('직접 써보기를 열 수 있다', () => {
    draw()

    fireEvent.click(practiceButtons()[0])

    expect(screen.getByText('작문 연습')).toBeTruthy()
    expect(screen.getByPlaceholderText('영어로 써 보세요')).toBeTruthy()
  })

  test('예문을 가리지 않으면 예문이 보인다', () => {
    draw()

    fireEvent.click(screen.getByRole('checkbox'))

    expect(screen.getByText(`“${EXPRESSIONS[0].example}”`)).toBeTruthy()
  })
})

describe('배치', () => {
  test('넓은 화면은 표로 그린다', () => {
    setViewport('wide')
    draw()

    expect(document.querySelector('table')).toBeTruthy()
  })

  test('좁은 화면에서는 표를 쓰지 않는다', () => {
    // 칸이 다섯이면 폰에서 어떤 열 너비를 줘도 읽히지 않는다. 가로로 밀게 하지 않는다.
    setViewport('narrow')
    draw()

    expect(document.querySelector('table')).toBeNull()
    expect(document.querySelectorAll('li').length).toBe(EXPRESSIONS.length)
  })

  test('한쪽만 DOM 에 있다 — 두 벌을 심어 놓고 CSS 로 숨기지 않는다', () => {
    // 두 벌이면 같은 글이 두 번 읽히고(스크린 리더), 검사도 하나뿐인지 물을 수 없다.
    setViewport('narrow')
    draw()

    expect(screen.getAllByText(EXPRESSIONS[0].expression)).toHaveLength(1)
  })
})

describe('별', () => {
  test('담아 두지 않은 표현은 빈 별로 그려진다', () => {
    draw()

    expect(star('enlist').textContent).toBe('☆')
    expect(star('enlist').getAttribute('aria-pressed')).toBe('false')
  })

  test('담아 둔 표현만 채운 별이 된다', () => {
    draw(fakeStore([item({ expression: 'refer to' })]))

    expect(star('refer to').textContent).toBe('★')
    expect(star('refer to').getAttribute('aria-pressed')).toBe('true')
    // 한 줄만 켜져야 한다. 전부 켜지거나 전부 꺼지면 토글이 의미가 없다.
    expect(star('enlist').textContent).toBe('☆')
  })

  test('빈 별을 누르면 담긴다', () => {
    const store = draw()
    fireEvent.click(star('enlist'))

    expect(store.added).toEqual(['enlist'])
  })

  test('쓴 기록이 없는 표현은 묻지 않고 바로 제외된다', () => {
    const store = draw(fakeStore([item({ id: 7, practice_count: 0 })]))
    fireEvent.click(star('refer to'))

    expect(store.removed).toEqual([7])
    expect(screen.queryByText(REMOVE_WARNING)).toBeNull()
  })
})

describe('쓴 기록이 있는 표현을 제외할 때', () => {
  function withHistory() {
    return draw(fakeStore([item({ id: 7, practice_count: 2 })]))
  }

  test('무엇이 사라지는지 말하고 한 번 더 묻는다', () => {
    const store = withHistory()
    fireEvent.click(star('refer to'))

    expect(screen.getByText(REMOVE_WARNING)).toBeTruthy()
    // 묻는 중에는 아직 아무것도 지우지 않는다.
    expect(store.removed).toEqual([])
  })

  test('경고 문구가 사라지는 것을 이름으로 말한다', () => {
    expect(REMOVE_WARNING).toContain('직접 써보기 기록이 사라집니다')
    expect(REMOVE_WARNING).toContain('계속 진행하시겠습니까')
  })

  test('예 를 누르면 제외된다', async () => {
    const store = withHistory()
    fireEvent.click(star('refer to'))
    fireEvent.click(screen.getByText('예'))

    await screen.findByText('refer to')
    expect(store.removed).toEqual([7])
  })

  test('아니오 를 누르면 아무 일도 없다', () => {
    const store = withHistory()
    fireEvent.click(star('refer to'))
    fireEvent.click(screen.getByText('아니오'))

    expect(store.removed).toEqual([])
    expect(screen.queryByText(REMOVE_WARNING)).toBeNull()
  })
})

describe('총평이 꼽은 표현', () => {
  test('별이 아니라 글자로 표시한다', () => {
    draw(fakeStore(), ['enlist'])

    const row = screen.getByText('enlist').closest('tr')!
    expect(row.textContent).toContain('핵심')
  })

  test('즐겨찾기와 같은 글자를 쓰지 않는다', () => {
    // 왼쪽 별이 즐겨찾기를 뜻하므로, 다른 뜻으로 ★ 를 또 쓰면 읽는 사람이 구별할 수 없다.
    draw(fakeStore(), ['enlist'])

    const row = screen.getByText('enlist').closest('tr')!
    const starText = star('enlist').textContent ?? ''
    expect(row.textContent?.replace(starText, '')).not.toContain('★')
  })
})
