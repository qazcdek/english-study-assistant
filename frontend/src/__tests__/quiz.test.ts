import { describe, expect, test } from 'vitest'

import { CHOICES, QUESTIONS, QUIZ_MIN, buildQuiz, canQuiz, shortBy, shuffled } from '../lib/quiz'
import type { VocabularyItem } from '../lib/types'

/**
 * 나의 표현 퀴즈 (M2-T8).
 *
 * 규약은 `lib/quiz.ts` 머리말. 여기서 지키는 것은 넷이다.
 *
 * - **오답지는 담아 둔 다른 뜻에서** — 지어내지 않는다
 * - **뜻이 겹치면 정답이 둘이 된다** — 뜻 글로 중복을 거른다
 * - **같은 표현을 두 번 묻지 않는다** — 한 판을 한 번에 만든다
 * - **랜덤을 인자로 받는다** — 안에서 부르면 검사가 흔들린다
 */

function item(expression: string, meaning: string, id = 0): VocabularyItem {
  return {
    id: id || expression.length,
    expression,
    type: '고급 어휘',
    meaning,
    example: '',
    example_ko: '',
    source_text: '',
    created_at: '2026-11-03T00:00:00Z',
    practice_count: 0,
  }
}

/** 섞지 않는 "섞기". **고정된 것을 넘겨** 검사가 흔들리지 않게 한다. */
const asIs = <T,>(list: T[]): T[] => [...list]

const SIX = [
  item('enlist', '동원하다'),
  item('refer to', '참조하다'),
  item('pass muster', '기준을 충족하다'),
  item('weigh in on', '의견을 내다'),
  item('sum up', '요약하다'),
  item('across the pond', '대서양을 건너'),
]

describe('퀴즈를 열 수 있나', () => {
  test(`표현이 ${QUIZ_MIN}개 미만이면 못 연다`, () => {
    // **탭의 `disabled` 가 이것을 쓴다** (사용자 결정).
    expect(canQuiz(SIX.slice(0, QUIZ_MIN - 1))).toBe(false)
    expect(canQuiz(SIX.slice(0, QUIZ_MIN))).toBe(true)
  })

  test('문제 수와 최소 개수가 같다', () => {
    // 다섯 문제를 내려면 다섯은 있어야 한다. 둘이 갈리면 짧은 판이 선다.
    expect(QUIZ_MIN).toBe(QUESTIONS)
  })
})

describe('한 판 만들기', () => {
  test(`문제마다 보기가 ${CHOICES}개이고 정답이 그 안에 있다`, () => {
    const quiz = buildQuiz(SIX, asIs)

    expect(quiz.length).toBe(QUESTIONS)
    for (const q of quiz) {
      expect(q.choices.length).toBe(CHOICES)
      expect(q.choices).toContain(q.answer)
    }
  })

  test('정답은 그 표현에 담아 둔 뜻이다', () => {
    const quiz = buildQuiz(SIX, asIs)

    for (const q of quiz) {
      const saved = SIX.find((i) => i.expression === q.expression)
      expect(q.answer).toBe(saved?.meaning)
    }
  })

  test('오답지는 **담아 둔 다른 뜻**에서만 온다', () => {
    // 지어내지 않는다. 회원이 실제로 담은 뜻들끼리 겨룬다.
    const meanings = new Set(SIX.map((i) => i.meaning))
    const quiz = buildQuiz(SIX, asIs)

    for (const q of quiz) {
      for (const choice of q.choices) expect(meanings.has(choice)).toBe(true)
    }
  })

  test('보기에 같은 글이 두 번 오지 않는다', () => {
    const quiz = buildQuiz(SIX, asIs)

    for (const q of quiz) {
      expect(new Set(q.choices).size).toBe(CHOICES)
    }
  })

  test('같은 표현을 두 번 묻지 않는다', () => {
    const quiz = buildQuiz(SIX, asIs)

    expect(new Set(quiz.map((q) => q.expression)).size).toBe(quiz.length)
  })

  test('표현이 다섯보다 적게 쓸 수 있으면 있는 만큼만 낸다', () => {
    // 뜻이 서로 다른 것이 넷뿐이면 네 문제다.
    const quiz = buildQuiz(SIX.slice(0, 4), asIs)

    expect(quiz.length).toBe(4)
  })
})

describe('뜻이 겹칠 때', () => {
  const DUPES = [
    item('sum up', '요약하다', 1),
    item('summarise', '요약하다', 2),
    item('recap', '요약하다', 3),
    item('enlist', '동원하다', 4),
    item('refer to', '참조하다', 5),
  ]

  test('정답이 둘이 되지 않는다', () => {
    // **표현이 다르다고 뜻이 다른 것이 아니다.** 겹친 뜻이 오답지에 올라가면
    // 정답이 둘이 된다.
    const quiz = buildQuiz(DUPES, asIs)

    for (const q of quiz) {
      expect(q.choices.filter((c) => c === q.answer).length).toBe(1)
    }
  })

  test('겹친 뜻은 한 번만 쓴다', () => {
    const quiz = buildQuiz(DUPES, asIs)

    // 서로 다른 뜻이 셋뿐이므로 오답 셋을 채울 수 없다 — 한 문제도 못 낸다.
    expect(quiz).toEqual([])
    expect(shortBy(DUPES)).toBe(1)
  })

  test('뜻이 빈 표현은 쓰지 않는다', () => {
    // 뜻이 없으면 물어볼 것도, 오답지로 쓸 것도 없다.
    const withBlank = [...SIX.slice(0, 4), item('blank', '  ')]

    const quiz = buildQuiz(withBlank, asIs)

    for (const q of quiz) {
      expect(q.expression).not.toBe('blank')
      for (const choice of q.choices) expect(choice.trim()).not.toBe('')
    }
  })

  test('뜻이 서로 다른 것이 넷을 못 넘으면 몇 개 모자란지 말한다', () => {
    expect(shortBy(SIX.slice(0, 2))).toBe(2)
    expect(shortBy(SIX)).toBe(0)
  })
})

describe('섞기', () => {
  test('받은 배열을 바꾸지 않는다', () => {
    // `vocab.items` 를 그대로 넘기므로 제자리에서 섞으면 **목록 화면의 순서가
    // 따라 바뀐다.**
    const original = [1, 2, 3, 4, 5]
    const copy = [...original]

    shuffled(original)

    expect(original).toEqual(copy)
  })

  test('원소를 잃거나 더하지 않는다', () => {
    const got = shuffled([1, 2, 3, 4, 5])

    expect([...got].sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5])
  })
})
