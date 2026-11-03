import type { VocabularyItem } from './types'

/** 한 문제. **정답이 몇 번인지 들고 있지 않는다** — 정답 글을 들고 비교한다.
 *
 *  번호로 들면 보기를 섞는 코드와 정답을 가리키는 코드가 **두 곳에서 짝을 맞춰야**
 *  하고, 한쪽만 고치면 조용히 틀린 채로 돈다. */
export interface Question {
  /** 물어보는 표현. `expression` 을 보고 뜻을 고른다. */
  expression: string
  /** 보기 넷. 섞여 있다. */
  choices: string[]
  /** 그중 맞는 것. `choices` 안에 반드시 있다. */
  answer: string
}

/** 한 문제에 필요한 보기 수 — 정답 하나 + 오답 셋. */
export const CHOICES = 4

/** 한 판의 문제 수. */
export const QUESTIONS = 5

/** 퀴즈를 열어 주는 최소 개수 (사용자 결정).
 *
 *  **문제 수와 같다** — 다섯 문제를 내려면 표현이 다섯은 있어야 하고, 그보다 적으면
 *  같은 표현이 거듭 나오거나 판이 짧아진다. 모자랄 때는 **탭 자체를 못 누르게**
 *  한다 — 들어가서 "못 한다" 를 읽는 것보다 애초에 안 열리는 쪽이 낫다. */
export const QUIZ_MIN = QUESTIONS

/** 퀴즈를 열 수 있나. **탭의 `disabled` 가 이것을 쓴다.** */
export function canQuiz(items: VocabularyItem[]): boolean {
  return items.length >= QUIZ_MIN
}

/**
 * 담아 둔 표현으로 퀴즈 한 판을 만든다 (M2-T8).
 *
 * ### 오답지는 담아 둔 다른 뜻에서 고른다
 *
 * 지어내지 않는다. 회원이 실제로 담은 뜻들이 보기로 올라오므로 **헷갈릴 만한 것들
 * 끼리** 겨루게 되고, LLM 을 부를 일도 없다.
 *
 * ### 뜻 글로 중복을 거른다
 *
 * 같은 뜻을 가진 표현이 둘이면 오답지에 **정답과 같은 글**이 올라가 정답이 둘이
 * 된다. 표현이 다르다고 뜻이 다른 것이 아니다 — `sum up` 과 `summarise` 가 둘 다
 * "요약하다" 일 수 있다.
 *
 * ### 뽑기를 인자로 받는다
 *
 * `Math.random` 을 안에서 부르면 **검사가 흔들린다.** 섞는 함수를 받아서, 검사는
 * 고정된 것을 넘기고 화면은 진짜 랜덤을 넘긴다.
 */
export function buildQuiz(
  items: VocabularyItem[],
  shuffle: <T>(list: T[]) => T[] = shuffled,
  count: number = QUESTIONS,
): Question[] {
  // 뜻이 비면 물어볼 수 없고, 뜻이 겹치면 정답이 둘이 된다.
  const byMeaning = new Map<string, VocabularyItem>()
  for (const item of items) {
    const meaning = item.meaning.trim()
    if (meaning && !byMeaning.has(meaning)) byMeaning.set(meaning, item)
  }
  const usable = [...byMeaning.values()]

  // 오답 셋을 뽑을 수 없으면 한 문제도 못 낸다.
  if (usable.length < CHOICES) return []

  const meanings = [...byMeaning.keys()]
  return shuffle(usable)
    .slice(0, count)
    .map((item) => {
      const answer = item.meaning.trim()
      const wrong = shuffle(meanings.filter((m) => m !== answer)).slice(0, CHOICES - 1)
      return { expression: item.expression, choices: shuffle([answer, ...wrong]), answer }
    })
}

/** 뜻이 겹쳐 문제를 못 낼 때 몇 개가 모자란가. 0 이면 낼 수 있다.
 *
 *  `canQuiz()` 와 **다른 것을 본다.** 그쪽은 개수(사용자가 정한 5개)이고 이쪽은
 *  **서로 다른 뜻**의 수다 — 다섯 개를 담았는데 뜻이 셋뿐이면(같은 뜻이 겹치면)
 *  오답지를 못 채운다. 드물지만 나면 빈 화면이 되므로 말로 알려 준다. */
export function shortBy(items: VocabularyItem[]): number {
  const meanings = new Set(
    items.map((i) => i.meaning.trim()).filter((m) => m.length > 0),
  )
  return Math.max(0, CHOICES - meanings.size)
}

/** Fisher–Yates. **받은 배열을 바꾸지 않는다** — `vocab.items` 를 넘기므로 섞으면
 *  목록 화면의 순서가 따라 바뀐다. */
export function shuffled<T>(list: T[]): T[] {
  const out = [...list]
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}
