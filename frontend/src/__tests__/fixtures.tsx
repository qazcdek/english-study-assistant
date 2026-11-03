import type {
  Account,
  AccountSettings,
  AppConfig,
  Examples,
  Expression,
  Level,
  VocabularyItem,
} from '../lib/types'
import type { VocabularyStore } from '../lib/useVocabulary'

export const SOURCE = 'We enlist a set of principles and refer to them during training.'

/** 예문 셋을 한 줄로 짓는다. 안 준 난이도는 **빈 쌍**이다 — 낡은 기록이 그 모양이다. */
export function examples(pairs: Partial<Record<Level, [string, string]>>): Examples {
  const at = (level: Level) => {
    const pair = pairs[level]
    return pair ? { en: pair[0], ko: pair[1] } : { en: '', ko: '' }
  }
  return { beginner: at('beginner'), intermediate: at('intermediate'), advanced: at('advanced') }
}

export const EXPRESSIONS: Expression[] = [
  {
    expression: 'enlist',
    type: '고급 어휘',
    meaning: '(도움·지지를) 얻다, 동원하다',
    // **난이도마다 길이가 다르다** (M16) — 고른 것이 실제로 바뀌는지를 검사가 물을 수 있다.
    examples: examples({
      beginner: ['They enlisted a panel.', '그들은 패널을 동원했다.'],
      intermediate: [
        'They enlisted a panel of experts who had studied the issue.',
        '그들은 그 문제를 연구해 온 전문가 패널을 동원했다.',
      ],
      advanced: [
        'Having exhausted every other option, they enlisted a panel of experts whose findings nobody disputed.',
        '다른 선택지를 모두 소진한 끝에, 그들은 누구도 반박하지 못한 결론을 낸 전문가 패널을 동원했다.',
      ],
    }),
  },
  {
    expression: 'refer to',
    type: 'Phrasal Verb',
    meaning: '참조하다',
    // **중급만 있는 표현.** 낡은 기록이 올라온 모양이다 — 초급·고급은 비어 있다.
    examples: examples({
      intermediate: ['Please refer to the appendix.', '부록을 참조해 주세요.'],
    }),
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


/**
 * 서버가 주는 설정의 모형. **한 곳에만 둔다** — 검사 파일마다 적으면 칸이 늘 때
 * 세 곳을 고쳐야 하고, 실제로 `providers` 를 더했을 때 세 곳이 깨졌다 (M12-T4).
 */
export function appConfig(overrides: Partial<AppConfig> = {}): AppConfig {
  return {
    mode: 'cloud',
    requires_login: true,
    default_model: 'gemini-3.5-flash-lite',
    daily_analysis_limit: 60,
    daily_practice_limit: 200,
    api_key_issue_url: '',
    max_input_chars: 1200,
    providers: [
      {
        id: 'gemini',
        label: 'Google Gemini',
        models: ['gemini-3.5-flash-lite'],
        needs_key: true,
        key_url: 'https://aistudio.google.com/apikey',
      },
    ],
    default_provider: 'gemini',
    ...overrides,
  }
}

export function accountSettings(overrides: Partial<AccountSettings> = {}): AccountSettings {
  return {
    active_provider: 'gemini',
    active_model: 'gemini-3.5-flash-lite',
    keys: {},
    ready: false,
    ...overrides,
  }
}

/** 로그인한 회원의 모형. 관문 판단이 이걸 본다. */
export function account(overrides: Partial<Account> = {}): Account {
  return {
    email: 'a@b.com',
    name: '테스터',
    picture: '',
    has_consented: true,
    has_api_key: false,
    api_key_hint: '',
    ...overrides,
  }
}
