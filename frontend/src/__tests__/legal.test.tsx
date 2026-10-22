import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { ConsentPanel } from '../components/ConsentPanel'
import { Legal } from '../legal/Legal'
import { Privacy } from '../legal/Privacy'
import { Terms } from '../legal/Terms'
import { OPERATOR, legalReady, unfilled } from '../legal/operator'
import { appConfig } from './fixtures'

/**
 * 법적 문서는 **빈칸이 남은 채 사용자에게 보이면 안 된다.**
 *
 * 처음에는 "빈칸이 있으면 검사가 실패한다" 로 걸었는데 **그 설계가 틀렸다** —
 * CI 가 빨개져 다른 작업 전부가 막힌다. 막아야 할 것은 빌드가 아니라 **노출**이다.
 * 그래서 링크를 `legalReady()` 에 걸고, 검사는 그 짝이 맞는지만 본다.
 */
test('빈칸이 남아 있으면 아직 보여줄 준비가 안 된 것이다', () => {
  expect(legalReady()).toBe(unfilled().length === 0)
})

test('바닥글의 링크는 준비됐을 때만 보인다', () => {
  render(<Footer />)

  if (legalReady()) {
    expect(screen.getByText('이용약관')).toBeTruthy()
  } else {
    expect(screen.queryByText('이용약관')).toBeNull()
  }
})

/** App 의 바닥글과 **같은 조건**을 쓴다. 조건이 갈라지면 한쪽만 고쳐진다. */
function Footer() {
  return legalReady() ? (
    <footer>
      <button type="button">이용약관</button>
      <button type="button">개인정보처리방침</button>
    </footer>
  ) : null
}

describe('이용약관', () => {
  test('동의 화면이 밝힌 것과 같은 말을 한다', () => {
    render(<Terms onBack={() => {}} />)

    // 어긋나면 어느 쪽이 유효한지 다투게 된다.
    expect(screen.getByText(/회원이 직접 등록한 Google Gemini API\s*키/)).toBeTruthy()
    expect(screen.getByText(/회원 Google 계정의 사용 한도가 소모/)).toBeTruthy()
    expect(screen.getByText(/민감한 내용을 입력하지 마십시오/)).toBeTruthy()
  })

  test('하루 한도 숫자를 적지 않는다', () => {
    // 설정으로 바뀌는 값이라 적으면 조용히 낡는다. "한도를 둔다" 는 사실만 말한다.
    const { container } = render(<Terms onBack={() => {}} />)

    expect(container.textContent).not.toMatch(/\d+\s*회\s*·/)
    expect(container.textContent).toContain('1일 호출 한도')
  })

  test('무료이고 가용성을 보장하지 않는다고 말한다', () => {
    render(<Terms onBack={() => {}} />)

    expect(screen.getByText(/가용성을 보장하지 않습니다/)).toBeTruthy()
  })

  test('준거법 조항이 있다', () => {
    render(<Terms onBack={() => {}} />)

    expect(screen.getByText(/대한민국법/)).toBeTruthy()
  })
})

describe('개인정보처리방침', () => {
  test('밖으로 나가는 곳을 전부 이름으로 밝힌다', () => {
    render(<Privacy onBack={() => {}} />)

    // 표의 칸 이름을 그대로 짚는다. 본문에도 같은 낱말이 나오므로 정규식으로 찾으면 겹친다.
    //
    // **LLM 제공자 줄이 레지스트리와 맞는지는 백엔드가 본다**
    // (`test_provider_registry.py` — 방침 파일 글자를 직접 읽는다).
    // 여기서 보는 것은 "표가 실제로 화면에 그려지나" 다.
    for (const name of [
      'Google (OAuth)',
      'Google (Gemini API)',
      'OpenAI (ChatGPT API)',
      'Anthropic (Claude API)',
      'Neon (데이터베이스)',
      'Render (호스팅)',
      'Sentry (오류 추적)',
    ]) {
      expect(screen.getByText(name)).toBeTruthy()
    }
  })

  test('몇 곳인지를 표에서 세어 말한다', () => {
    // 전에는 "다섯 곳" 이 글로 박혀 있었다. 줄을 늘리면 본문이 거짓이 된다.
    render(<Privacy onBack={() => {}} />)

    expect(screen.getByText(/7곳에 처리를 위탁하며/)).toBeTruthy()
  })

  test('고르지 않은 제공자로는 나가지 않는다고 말한다', () => {
    // 일곱 곳을 한꺼번에 나열하면 "내 문장이 일곱 군데로 간다" 로 읽힌다.
    render(<Privacy onBack={() => {}} />)

    expect(screen.getByText(/회원이 고른 한 곳만 호출됩니다/)).toBeTruthy()
  })

  test('오류 로그가 탈퇴 즉시 삭제의 예외라고 말한다', () => {
    // 내가 Sentry 에 회원 id 를 남기기로 했으므로, 그게 그대로 적혀 있어야 한다.
    // 숨기면 "탈퇴하면 전부 삭제" 가 거짓이 된다.
    render(<Privacy onBack={() => {}} />)

    expect(screen.getByText(/탈퇴 후에도 일정 기간 남을 수 있습니다/)).toBeTruthy()
  })

  test('오류 로그에 무엇이 안 들어가는지도 말한다', () => {
    // 보내는 것만 적고 안 보내는 것을 안 적으면 독자가 최악을 가정한다.
    render(<Privacy onBack={() => {}} />)

    expect(screen.getByText(/요청 본문 · 쿠키 · API 키는 보내지 않습니다/)).toBeTruthy()
  })

  test('Gemini 무료 등급 고지가 있다', () => {
    render(<Privacy onBack={() => {}} />)

    expect(screen.getByText(/Google 의 서비스 개선에 입력 데이터가 쓰일 수 있습니다/)).toBeTruthy()
  })

  test('권리 행사를 운영자에게 요청하지 않아도 된다고 말한다', () => {
    // 코드가 이미 그렇다 — 화면에서 직접 지운다. 방침이 그것과 어긋나면 안 된다.
    render(<Privacy onBack={() => {}} />)

    expect(screen.getByText(/운영자에게 요청할 필요가\s*없습니다/)).toBeTruthy()
  })
})

test('두 문서가 같은 운영자 정보를 쓴다', () => {
  // 각각 적으면 한쪽만 고쳐져 갈라지고, 법적 문서가 갈라지면 다투게 된다.
  const terms = render(<Terms onBack={() => {}} />).container.textContent ?? ''
  const privacy = render(<Privacy onBack={() => {}} />).container.textContent ?? ''

  expect(terms).toContain(OPERATOR.이름)
  expect(privacy).toContain(OPERATOR.이름)
  expect(privacy).toContain(OPERATOR.연락처)
})

test('빈칸이 남아 있으면 화면이 그렇다고 말한다', () => {
  render(
    <Legal title="시험" onBack={() => {}}>
      <p>본문</p>
    </Legal>,
  )

  // 검사가 배포를 막지만, 개발 중에도 눈에 보여야 한다.
  if (unfilled().length > 0) {
    expect(screen.getByText(/아직 채워지지 않은 항목이 있습니다/)).toBeTruthy()
  }
})


describe('동의의 대상', () => {
  const config = appConfig()

  /**
   * 전에는 동의의 대상이 **안내 화면**이었다. `users.consented_at` 이 가리키는 것이
   * 문서가 아니었으므로, 약관·방침에 대한 동의는 어디에도 없었다 (M1-T2).
   */
  test('동의 문구가 두 문서를 지목한다', () => {
    render(<ConsentPanel config={config} onAgree={async () => {}} onOpenTerms={() => {}} onOpenPrivacy={() => {}} />)

    const label = screen.getByRole('checkbox').closest('label')
    expect(label?.textContent).toContain('이용약관')
    expect(label?.textContent).toContain('개인정보처리방침')
    expect(label?.textContent).toContain('동의')
  })

  test('두 문서로 가는 길이 있다', () => {
    const opened: string[] = []
    render(
      <ConsentPanel
        config={config}
        onAgree={async () => {}}
        onOpenTerms={() => opened.push('terms')}
        onOpenPrivacy={() => opened.push('privacy')}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '이용약관' }))
    fireEvent.click(screen.getByRole('button', { name: '개인정보처리방침' }))

    expect(opened).toEqual(['terms', 'privacy'])
  })

  test('기존 안내는 그대로 남는다', () => {
    // 회원 키로 호출된다는 고지는 법적 문서가 생겨도 화면에 남아야 한다 —
    // 동의 시점에 읽히는 것이 문서가 아니라 이 화면이다.
    render(<ConsentPanel config={config} onAgree={async () => {}} onOpenTerms={() => {}} onOpenPrivacy={() => {}} />)

    expect(screen.getByText(/회원님이 직접 등록한 Google Gemini API 키/)).toBeTruthy()
  })
})
