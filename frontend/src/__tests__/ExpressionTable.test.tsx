import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { ExpressionTable, REMOVE_WARNING } from '../components/ExpressionTable'
import { EXPRESSIONS, SOURCE, fakeStore, item } from './fixtures'

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

/** 표현 한 줄의 별 버튼. 라벨이 상태를 말하므로 그걸로 찾는다. */
function star(expression: string) {
  const row = screen.getByText(expression).closest('tr')
  if (!row) throw new Error(`${expression} 행을 못 찾았다`)
  const button = row.querySelector('button[aria-pressed]')
  if (!button) throw new Error(`${expression} 행에 별이 없다`)
  return button as HTMLButtonElement
}

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
