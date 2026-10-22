import type { Expression, VocabularyItem } from '../lib/types'
import type { VocabularyStore } from '../lib/useVocabulary'

export const SOURCE = 'We enlist a set of principles and refer to them during training.'

export const EXPRESSIONS: Expression[] = [
  {
    expression: 'enlist',
    type: '고급 어휘',
    meaning: '(도움·지지를) 얻다, 동원하다',
    example: 'They enlisted a panel of experts.',
    example_ko: '그들은 전문가 패널을 동원했다.',
  },
  {
    expression: 'refer to',
    type: 'Phrasal Verb',
    meaning: '참조하다',
    example: 'Please refer to the appendix.',
    example_ko: '부록을 참조해 주세요.',
  },
]

export function item(overrides: Partial<VocabularyItem> = {}): VocabularyItem {
  return {
    id: 1,
    expression: 'refer to',
    type: 'Phrasal Verb',
    meaning: '참조하다',
    example: 'Please refer to the appendix.',
    example_ko: '부록을 참조해 주세요.',
    source_text: SOURCE,
    created_at: '2026-10-22T00:00:00+00:00',
    practice_count: 0,
    ...overrides,
  }
}

/**
 * 가짜 나의 표현 저장소. 서버를 안 타고 **무엇이 불렸는지**만 기록한다.
 *
 * 실제 호출까지 확인하는 것은 백엔드 테스트의 몫이다(`test_both_modes.py`).
 * 여기서 보는 것은 화면이 **어떤 상황에서 무엇을 부르는가**다.
 */
export function fakeStore(items: VocabularyItem[] = []): VocabularyStore & {
  added: string[]
  removed: number[]
} {
  const byExpression = new Map(items.map((i) => [i.expression, i]))
  const added: string[] = []
  const removed: number[] = []
  return {
    items,
    added,
    removed,
    has: (expression) => byExpression.has(expression),
    practiceCount: (expression) => byExpression.get(expression)?.practice_count ?? 0,
    idOf: (expression) => byExpression.get(expression)?.id ?? null,
    add: async (expression) => {
      added.push(expression.expression)
    },
    remove: async (id) => {
      removed.push(id)
      return { ok: true, expression: '', practices_deleted: 0 }
    },
    reload: async () => {},
  }
}


/**
 * 화면 너비를 가장한다. jsdom 에는 `matchMedia` 가 없어서 기본값은 **넓은 쪽**이다.
 *
 * 좁은 쪽을 보려면 일부러 꽂아야 한다 — 그래야 "좁은 화면에서 뭐가 보이나" 를
 * 검사가 물을 수 있다. 창을 끌어 늘리는 경우(`change` 이벤트)는 여기서 다루지 않는다.
 */
export function setViewport(kind: 'wide' | 'narrow') {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (media: string) => ({
      media,
      matches: kind === 'wide',
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}
