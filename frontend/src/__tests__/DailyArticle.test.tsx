import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import type { AnalysisResult, DailyArticle as Article, MarkdownSections } from '../lib/types'

const getDailyArticle = vi.fn()
const getParagraphAnalysis = vi.fn()

// 서버를 안 띄우고 **두 호출만** 바꿔 꽂는다. 이 화면이 보는 것은
// "어떤 상황에서 무엇을 부르는가" 이고, 실제 응답은 백엔드 검사가 본다
// (`test_daily.py`).
vi.mock('../lib/api', () => ({
  getDailyArticle: () => getDailyArticle(),
  getParagraphAnalysis: (id: number, ordinal: number) => getParagraphAnalysis(id, ordinal),
  gradePractice: vi.fn(),
  listPracticeHistory: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      readonly code: string,
      message: string,
    ) {
      super(message)
    }
  },
}))

const { DailyArticle, dayLabel, sourceLabel } = await import('../components/DailyArticle')
const { ApiError } = await import('../lib/api')
const { finishedState } = await import('../lib/analysis')
const { EXPRESSIONS, fakeStore } = await import('./fixtures')

const BODY = [
  'Ukraine has resumed long-range strikes on Russian oil refineries, officials said.',
  'The decision came days after Washington urged both sides to hold their fire.',
  'Analysts warned the campaign could push fuel prices higher through the winter.',
]

function article(overrides: Partial<Article> = {}): Article {
  return {
    id: 7,
    source: 'guardian',
    url: 'https://www.theguardian.com/world/2026/nov/01/example',
    title: 'Ukraine defies Trump to resume attacks on Russian oil refineries',
    byline: 'Luke Harding in Kyiv',
    section: 'world',
    published_at: '2026-11-01T06:00:00+00:00',
    picked_for: '2026-11-01',
    level: 'intermediate',
    paragraphs: BODY.map((text, i) => ({ ordinal: i + 1, text, prepared: true })),
    ...overrides,
  }
}

function result(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    source_text: BODY[0],
    translation: '우크라이나가 러시아 정유시설에 대한 장거리 타격을 재개했다.',
    expressions: EXPRESSIONS,
    structures: [],
    overview: {
      domain: '국제 시사',
      tone: '건조한 보도체',
      formality: '격식',
      style: '문어체',
      key_expressions: ['resume'],
      comment: '보도문에서 자주 보이는 구성이다.',
    },
    ...overrides,
  }
}

const MARKDOWN: MarkdownSections = {
  translation: '### 자연스러운 번역\n우크라이나가…',
  expressions: '### 표현 풀이',
  structures: '### 문장 구조',
  overview: '### 총평',
  full: '### 자연스러운 번역\n우크라이나가…',
}

function analysis(overrides: Record<string, unknown> = {}) {
  return {
    ordinal: 1,
    level: 'intermediate',
    result: result(),
    markdown: MARKDOWN,
    failed_parts: [],
    model: 'gemini-3.5-flash-lite',
    ...overrides,
  }
}

function draw(level: 'beginner' | 'intermediate' | 'advanced' = 'intermediate') {
  render(<DailyArticle vocab={fakeStore()} level={level} />)
}

beforeEach(() => {
  getDailyArticle.mockReset()
  getParagraphAnalysis.mockReset()
  getDailyArticle.mockResolvedValue({ article: article() })
  getParagraphAnalysis.mockResolvedValue(analysis())
})

describe('글감이 없을 때', () => {
  test('오류가 아니라 기다리는 상태로 알려준다', async () => {
    // 첫 배포 직후와 고르기가 실패하는 동안의 **정상 상태**다.
    getDailyArticle.mockResolvedValue({ article: null })
    draw()

    expect(await screen.findByText(/아직 준비된 글감이 없습니다/)).toBeTruthy()
  })

  test('서버가 터진 것은 오류로 알려준다', async () => {
    getDailyArticle.mockRejectedValue(new ApiError('network', '서버에 연결할 수 없습니다.'))
    draw()

    expect(await screen.findByText('서버에 연결할 수 없습니다.')).toBeTruthy()
    expect(screen.queryByText(/아직 준비된 글감이 없습니다/)).toBeNull()
  })
})

describe('글감 머리', () => {
  test('며칠 글감인지 적는다', async () => {
    // 오늘 것이 없으면 어제 것이 온다 (09 §3.8). **언제 것인지 모르고 읽으면 안 된다.**
    draw()

    expect(await screen.findByText(/11월 1일 글감/)).toBeTruthy()
  })

  test('원문 백링크를 위아래 둘 다 둔다', async () => {
    // **약관이 요구한다** — 번역 본문 상단이나 하단에 원문으로 가는 링크를 반드시
    // 건다. 문단 아코디언이라 번역이 화면 중간에서 펼쳐지므로 둘 다 둔다 (M13-T10).
    draw()

    await screen.findByText(/11월 1일 글감/)
    const links = screen.getAllByText(/원문 보기/) as HTMLAnchorElement[]

    expect(links.length).toBe(2)
    for (const link of links) {
      expect(link.getAttribute('href')).toBe(article().url)
      // 글감을 읽다가 앱을 떠나지 않게 새 탭으로 연다.
      expect(link.getAttribute('target')).toBe('_blank')
    }
  })

  test('기자 크레딧과 출처를 적는다', async () => {
    // **약관이 요구한다** — 기자 이름과 원문 출처를 명확히. `guardian` 이 아니라
    // 약관이 쓰는 이름(`The Guardian`)으로 적는다.
    draw()

    const credits = await screen.findAllByText(/Luke Harding in Kyiv/)

    expect(credits.length).toBe(2) // 머리와 바닥
    for (const credit of credits) expect(credit.textContent).toContain('The Guardian')
  })

  test('발췌임을 숨기지 않는다', async () => {
    // 전문이 아니라 500단어 이내의 토막이다 (M13-T9). 전문처럼 보이게 두지 않는다.
    draw()

    const note = await screen.findByText(/발췌해 번역했습니다/)
    expect(note.textContent).toContain('500단어')
  })

  test('**준비된** 난이도를 적는다. 회원이 고른 것이 아니다', async () => {
    // 미리 분석은 중급 하나만 돌아 있다. 초급을 고른 회원에게도 중급이라고 적는다 —
    // 회원 난이도로 바꿔 적으면 화면이 거짓말을 한다.
    draw('beginner')

    const note = await screen.findByText(/으로 미리 분석/)
    expect(note.textContent).toContain('중급')
    expect(note.textContent).toContain('문단 3개')
  })
})

describe('문단', () => {
  test('본문은 다 보여주고 분석은 아직 안 가져온다', async () => {
    // 한 편을 통째로 받으면 128KB 다. 펼칠 때 하나씩 가져온다.
    draw()

    for (const text of BODY) expect(await screen.findByText(text)).toBeTruthy()
    expect(getParagraphAnalysis).not.toHaveBeenCalled()
  })

  test('펼친 문단 하나만 가져온다', async () => {
    draw()

    fireEvent.click(await screen.findByText(BODY[1]))

    await waitFor(() => expect(getParagraphAnalysis).toHaveBeenCalledWith(7, 2))
    expect(getParagraphAnalysis).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(/자연스러운 번역/)).toBeTruthy()
  })

  test('접었다 다시 펴도 다시 묻지 않는다', async () => {
    draw()

    const paragraph = await screen.findByText(BODY[0])
    fireEvent.click(paragraph)
    await waitFor(() => expect(getParagraphAnalysis).toHaveBeenCalledTimes(1))
    fireEvent.click(paragraph)
    fireEvent.click(paragraph)

    expect(await screen.findByText(/자연스러운 번역/)).toBeTruthy()
    expect(getParagraphAnalysis).toHaveBeenCalledTimes(1)
  })

  test('준비되지 않은 문단은 묻지 않고 그렇다고 말한다', async () => {
    // 미리 분석이 중간에 멈추면 뒤쪽 문단이 이 상태다. 물으면 404 가 날 것을
    // 이미 알고 있으므로 **부르지 않는다.**
    const paragraphs = article().paragraphs.map((p) => ({ ...p, prepared: p.ordinal === 1 }))
    getDailyArticle.mockResolvedValue({ article: article({ paragraphs }) })
    draw()

    fireEvent.click(await screen.findByText(BODY[2]))

    expect(await screen.findByText(/아직 분석이 준비되지 않았습니다/)).toBeTruthy()
    expect(getParagraphAnalysis).not.toHaveBeenCalled()
  })

  test('한 문단을 못 가져와도 나머지는 그대로 읽는다', async () => {
    getParagraphAnalysis.mockRejectedValue(
      new ApiError('not_found', '아직 준비되지 않은 문단입니다.'),
    )
    draw()

    fireEvent.click(await screen.findByText(BODY[0]))

    expect(await screen.findByText('아직 준비되지 않은 문단입니다.')).toBeTruthy()
    // 본문은 사라지지 않는다.
    for (const text of BODY) expect(screen.getByText(text)).toBeTruthy()
  })

  test('미리 분석에는 소요 시간이 없다 — 그래도 진행 중이라고 하지 않는다', async () => {
    // `meta` 가 없으면 `ResultView` 가 끝난 분석을 "분석하는 중" 으로 읽었다.
    // 모델과 난이도를 적어 그 자리를 채운다.
    draw()

    fireEvent.click(await screen.findByText(BODY[0]))

    expect(await screen.findByText(/중급 분석 · gemini-3.5-flash-lite/)).toBeTruthy()
    expect(screen.queryByText(/파트별로 분석하는 중/)).toBeNull()
  })
})

describe('이미 끝난 분석을 화면 상태로', () => {
  test('실패한 파트만 실패로 표시한다', () => {
    // 전부 `done` 으로 칠하면 **빈 칸이 "결과 없음" 처럼 보인다.**
    const state = finishedState(result(), MARKDOWN, ['overview'])

    expect(state.status.translation.state).toBe('done')
    expect(state.status.overview.state).toBe('error')
    expect(state.fullMarkdown).toBe(MARKDOWN.full)
  })

  test('실패한 파트가 없으면 전부 끝난 것이다', () => {
    const state = finishedState(result(), MARKDOWN)

    expect(Object.values(state.status).every((s) => s.state === 'done')).toBe(true)
  })
})

describe('출처 이름', () => {
  test('약관이 쓰는 이름으로 적는다', () => {
    expect(sourceLabel('guardian')).toBe('The Guardian')
  })

  test('모르는 출처는 받은 값을 그대로 둔다', () => {
    // 꾸며 내면 크레딧이 틀린다. 출처가 늘 때 **여기서 걸려** 눈에 띄는 쪽이 낫다.
    expect(sourceLabel('npr')).toBe('npr')
  })
})

describe('날짜 표기', () => {
  test('읽기 좋은 날로 바꾼다', () => {
    expect(dayLabel('2026-11-01')).toBe('11월 1일')
    expect(dayLabel('2026-01-09')).toBe('1월 9일')
  })

  test('날짜가 아니면 꾸미지 않는다', () => {
    // 없는 날짜를 그럴듯하게 만들지 않는다.
    expect(dayLabel('')).toBe('')
    expect(dayLabel('언젠가')).toBe('언젠가')
  })
})
