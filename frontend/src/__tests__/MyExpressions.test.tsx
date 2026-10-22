import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import type { PracticeHistoryItem, VocabularyItem } from '../lib/types'

const listPracticeHistory = vi.fn<(expression?: string) => Promise<PracticeHistoryItem[]>>()

// 목록은 펼칠 때 서버에서 기록을 가져온다. 서버를 안 띄우고 그 한 함수만 바꿔 꽂는다.
vi.mock('../lib/api', () => ({
  listPracticeHistory: (expression?: string) => listPracticeHistory(expression),
  gradePractice: vi.fn(),
  ApiError: class ApiError extends Error {},
}))

const { MyExpressions, stamp, asExpression, groupByPrompt } = await import(
  '../components/MyExpressions',
)
const { REMOVE_WARNING } = await import('../components/ExpressionTable')
const { fakeStore, item } = await import('./fixtures')

const RECORD: PracticeHistoryItem = {
  id: 11,
  expression: 'refer to',
  prompt_ko: '부록을 참조해 주세요.',
  model_answer: 'Please refer to the appendix.',
  learner_answer: 'Please refer the appendix.',
  verdict: '통함',
  uses_target: true,
  feedback: {
    verdict: '통함',
    uses_target: true,
    good_point: '명령문 어순이 자연스럽다.',
    target_note: 'refer 는 to 를 반드시 끼운다.',
    corrected: 'Please refer to the appendix for the full table.',
    other_notes: ['the 를 빼도 된다.'],
  },
  created_at: '2026-10-22T14:05:09+09:00',
}

function draw(items: VocabularyItem[]) {
  const store = fakeStore(items)
  render(<MyExpressions vocab={store} level="intermediate" />)
  return store
}

beforeEach(() => {
  listPracticeHistory.mockReset()
  listPracticeHistory.mockResolvedValue([RECORD])
})

describe('목록', () => {
  test('담아 둔 것이 없으면 어떻게 담는지 알려준다', () => {
    draw([])

    const empty = screen.getByText(/아직 담아 둔 표현이 없습니다/)
    // 들어오는 길이 둘이다. 둘 다 말해야 한다.
    expect(empty.textContent).toContain('☆')
    expect(empty.textContent).toContain('직접 써보기')
  })

  test('접힌 채로는 예문을 보여주지 않는다', () => {
    // 답을 먼저 보면 복습이 성립하지 않는다.
    draw([item({ practice_count: 1 })])

    expect(screen.queryByText(/Please refer to the appendix/)).toBeNull()
  })
})

describe('나의 기록 보기', () => {
  test('접었다 폈다 한다', async () => {
    draw([item({ practice_count: 1 })])
    expect(screen.queryByText(RECORD.prompt_ko)).toBeNull()

    fireEvent.click(screen.getByText(/나의 기록 보기/))
    expect(await screen.findByText(RECORD.prompt_ko)).toBeTruthy()

    fireEvent.click(screen.getByText(/접기/))
    expect(screen.queryByText(RECORD.prompt_ko)).toBeNull()
  })

  test('그 표현의 기록만 가져온다', async () => {
    draw([item({ practice_count: 1 })])
    fireEvent.click(screen.getByText(/나의 기록 보기/))
    await screen.findByText(RECORD.prompt_ko)

    // 전부 가져와서 걸러내면 목록이 커질수록 느려진다.
    expect(listPracticeHistory).toHaveBeenCalledWith('refer to')
  })

  test('쓴 기록이 없어도 접었다 펼 수 있고, 없다고 말한다', async () => {
    listPracticeHistory.mockResolvedValue([])
    draw([item({ practice_count: 0 })])

    fireEvent.click(screen.getByText(/나의 기록 보기/))
    expect(await screen.findByText(/아직 직접 써본 기록이 없습니다/)).toBeTruthy()
  })
})

describe('제시문 묶음', () => {
  async function open(rows = [RECORD]) {
    listPracticeHistory.mockResolvedValue(rows)
    draw([item({ practice_count: rows.length })])
    fireEvent.click(screen.getByText(/나의 기록 보기/))
    await screen.findByText(rows[0].prompt_ko)
  }

  test('제시문만 보이고 내 답안은 접혀 있다', async () => {
    await open()

    expect(screen.getByText(RECORD.prompt_ko)).toBeTruthy()
    expect(screen.getByText(/내가 쓴 답안 보기/)).toBeTruthy()
    // 접힌 채로 답안까지 깔면 훑을 수가 없다.
    expect(screen.queryByText(RECORD.learner_answer)).toBeNull()
  })

  test('같은 제시문으로 쓴 답안은 한 묶음이 된다', async () => {
    const again = { ...RECORD, id: 12, learner_answer: 'Please refer to the appendix.' }
    await open([RECORD, again])

    // 제시문이 시도마다 반복되면 정작 다른 부분인 내 문장이 묻힌다.
    expect(screen.getAllByText(RECORD.prompt_ko)).toHaveLength(1)
    expect(screen.getAllByText(/내가 쓴 답안 보기/)).toHaveLength(1)

    fireEvent.click(screen.getByText(/내가 쓴 답안 보기/))
    expect(screen.getByText(RECORD.learner_answer)).toBeTruthy()
    expect(screen.getByText(again.learner_answer)).toBeTruthy()
  })

  test('제시문이 다르면 묶음도 갈린다', async () => {
    const other = { ...RECORD, id: 13, prompt_ko: '자세한 내용은 부록에 있다.' }
    await open([RECORD, other])

    expect(screen.getAllByText(/내가 쓴 답안 보기/)).toHaveLength(2)
    expect(screen.getByText(other.prompt_ko)).toBeTruthy()
  })

  test('묶는 순서는 서버가 준 최신순을 그대로 쓴다', () => {
    const other = { ...RECORD, id: 13, prompt_ko: '자세한 내용은 부록에 있다.' }
    const grouped = groupByPrompt([RECORD, other, { ...RECORD, id: 14 }])

    expect(grouped.map(([prompt]) => prompt)).toEqual([RECORD.prompt_ko, other.prompt_ko])
    expect(grouped[0][1].map((r) => r.id)).toEqual([RECORD.id, 14])
  })
})

describe('내가 쓴 답안 한 건', () => {
  async function open() {
    draw([item({ practice_count: 1 })])
    fireEvent.click(screen.getByText(/나의 기록 보기/))
    fireEvent.click(await screen.findByText(/내가 쓴 답안 보기/))
    const sentence = await screen.findByText(RECORD.learner_answer)
    return sentence.closest('li') as HTMLElement
  }

  test('접힌 채로는 내 문장과 일시만 보여준다', async () => {
    const answer = await open()

    expect(answer.textContent).toContain(RECORD.learner_answer)
    const time = answer.querySelector('time')
    expect(time?.textContent).toBe(stamp(RECORD.created_at))
    // 평가는 자세히 보기 안에 있다.
    expect(answer.textContent).not.toContain(RECORD.feedback.good_point)
    expect(answer.textContent).not.toContain(RECORD.model_answer)
    expect(answer.textContent).not.toContain('통함')
  })

  test('일시는 연월일 시분초다', async () => {
    const answer = await open()

    // 날짜만으로는 같은 날 여러 번 쓴 것이 구별되지 않는다.
    expect(answer.querySelector('time')?.textContent).toMatch(
      /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/,
    )
  })

  test('자세히 보기를 누르면 모범 답안과 그때 AI 가 매긴 평가가 나온다', async () => {
    const answer = await open()

    fireEvent.click(within(answer).getByText(/자세히 보기/))

    for (const text of [
      RECORD.model_answer,
      RECORD.feedback.good_point,
      RECORD.feedback.target_note,
      RECORD.feedback.corrected,
      RECORD.feedback.other_notes[0],
    ]) {
      expect(within(answer).getByText(text)).toBeTruthy()
    }
    expect(within(answer).getByText(/통함/)).toBeTruthy()
  })

  test('다시 누르면 접힌다', async () => {
    const answer = await open()

    fireEvent.click(within(answer).getByText(/자세히 보기/))
    fireEvent.click(within(answer).getByText(/접기/))

    expect(answer.textContent).not.toContain(RECORD.feedback.good_point)
  })
})

describe('복습', () => {
  test('예문과 제시문이 있으면 직접 써보기를 할 수 있다', () => {
    draw([item()])

    expect(screen.getByText(/직접 써보기/)).toBeTruthy()
  })

  test('제시문이 없으면 연습 입구를 주지 않는다', () => {
    // 분석 화면과 같은 조건이다. 한국어 제시문이 없으면 출제할 수 없다.
    draw([item({ example_ko: '' })])

    expect(screen.queryByText(/✏ 직접 써보기/)).toBeNull()
  })

  test('열면 분석 화면과 같은 연습 상자가 뜬다', () => {
    draw([item()])

    fireEvent.click(screen.getByText(/✏ 직접 써보기/))

    expect(screen.getByText('작문 연습')).toBeTruthy()
    // 한국어 제시문을 보여주고 영어를 묻는다 — 예문은 가려져 있다.
    expect(screen.getByText(item().example_ko)).toBeTruthy()
    expect(screen.getByPlaceholderText('영어로 써 보세요')).toBeTruthy()
  })

  test('연습에 넘기는 모양이 분석 결과의 표현과 같다', () => {
    const row = item()

    // 비슷한 것을 하나 더 만들지 않고 같은 컴포넌트에 같은 모양을 넘긴다.
    expect(asExpression(row)).toEqual({
      expression: row.expression,
      type: row.type,
      meaning: row.meaning,
      example: row.example,
      example_ko: row.example_ko,
    })
  })

  test('유형이 비어 있어도 연습할 수 있다', () => {
    // 연습으로 자동 등록된 옛 행은 type 이 빌 수 있다. 그걸로 막히면 안 된다.
    expect(asExpression(item({ type: '' })).type).toBeTruthy()
  })
})

describe('제외', () => {
  test('쓴 기록이 없으면 묻지 않는다', () => {
    const store = draw([item({ id: 5, practice_count: 0 })])

    fireEvent.click(screen.getByText('제외'))

    expect(store.removed).toEqual([5])
    expect(screen.queryByText(REMOVE_WARNING)).toBeNull()
  })

  test('쓴 기록이 있으면 무엇이 사라지는지 말하고 묻는다', () => {
    const store = draw([item({ id: 5, practice_count: 2 })])

    fireEvent.click(screen.getByText('제외'))

    expect(screen.getByText(REMOVE_WARNING)).toBeTruthy()
    expect(store.removed).toEqual([])
  })

  test('아니오 를 누르면 남는다', () => {
    const store = draw([item({ id: 5, practice_count: 2 })])

    fireEvent.click(screen.getByText('제외'))
    fireEvent.click(screen.getByText('아니오'))

    expect(store.removed).toEqual([])
  })

  test('기본 포커스는 아니오 다 — 엔터로 지워 버리는 일이 없어야 한다', () => {
    draw([item({ practice_count: 2 })])
    fireEvent.click(screen.getByText('제외'))

    expect(document.activeElement?.textContent).toBe('아니오')
  })
})
