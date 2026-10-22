import { Clause, Items, Legal } from './Legal'
import { OPERATOR } from './operator'

/**
 * 밖으로 나가는 곳 전부. 사용자가 **이름·국가·항목까지** 밝히기로 정했다.
 *
 * **LLM 제공자 줄은 레지스트리를 따라간다.** 고를 수 있는 제공자가 늘면 데이터가
 * 나가는 곳이 늘어나므로 이 표도 함께 늘어야 한다. 빼먹으면 **적지 않은 곳으로
 * 데이터가 나간다** — 그래서 `ProviderInfo.transfer_name` 의 글자가 이 표에 있는지
 * 검사가 본다 (`backend/tests/test_provider_registry.py`).
 *
 * 개수는 세지 않고 `TRANSFERS.length` 로 쓴다. 숫자를 글로 적어 두면 줄을 늘릴 때
 * 한쪽만 고치고 끝난다 (M12-T5).
 */
const TRANSFERS = [
  {
    받는곳: 'Google (OAuth)',
    국가: '미국 등',
    항목: '이메일 · 이름 · 프로필 사진 · 계정 식별자',
    목적: '로그인 (신원 확인만)',
  },
  {
    받는곳: 'Google (Gemini API)',
    국가: '미국 등',
    항목: '회원이 입력한 영어 원문, 회원이 쓴 영작 문장',
    목적: '문장 분석과 작문 연습 채점 — 회원 본인 API 키로 호출',
  },
  {
    받는곳: 'OpenAI (ChatGPT API)',
    국가: '미국 등',
    항목: '회원이 입력한 영어 원문, 회원이 쓴 영작 문장',
    목적: '문장 분석과 작문 연습 채점 — 회원 본인 API 키로 호출',
  },
  {
    받는곳: 'Anthropic (Claude API)',
    국가: '미국 등',
    항목: '회원이 입력한 영어 원문, 회원이 쓴 영작 문장',
    목적: '문장 분석과 작문 연습 채점 — 회원 본인 API 키로 호출',
  },
  {
    받는곳: 'Neon (데이터베이스)',
    국가: '미국 등',
    항목: '계정 정보 · 분석 기록 · 연습 기록 · 나의 표현 · 사용량. 암호화된 API 키 포함',
    목적: '기기 간 동기화를 위한 보관',
  },
  {
    받는곳: 'Render (호스팅)',
    국가: '미국 등',
    항목: '서비스 요청이 지나가는 모든 데이터',
    목적: '서비스 구동',
  },
  {
    받는곳: 'Sentry (오류 추적)',
    국가: '미국 등',
    항목: '예외 메시지 · 스택 · 요청 경로 · 회원 식별자(id)',
    목적: '오류 원인 파악',
  },
]

/**
 * 개인정보처리방침.
 *
 * **코드가 근거인 부분은 사실대로 적는다.** 특히 둘을 숨기지 않았다 —
 *
 * 1. Sentry 로그에 **회원 식별자(id)** 가 들어간다. "몇 명에게 났는지" 를 세려고 남긴
 *    설계상의 선택이고(`app/observability.py`), 그래서 **탈퇴 즉시 삭제가 로그에는
 *    그대로 적용되지 않는다.** 적지 않으면 3조가 거짓이 된다.
 * 2. Gemini 무료 등급은 Google 의 서비스 개선에 데이터가 쓰일 수 있다. 동의 화면이
 *    이미 밝히고 있으므로 방침도 같은 말을 해야 한다.
 *
 * 근거: 14-data-layer.md §2 · 07-web-deployment.md §9.1
 */
export function Privacy({ onBack }: { onBack: () => void }) {
  return (
    <Legal title="개인정보처리방침" onBack={onBack}>
      <p>
        {OPERATOR.이름}(이하 “운영자”)은 English Study Assistant(이하 “서비스”)를 개인으로
        운영하며, 아래와 같이 개인정보를 처리합니다.
      </p>

      <Clause n={1} title="수집하는 항목">
        <Items
          items={[
            <>
              <b>Google 로그인에서</b> — 이메일, 이름, 프로필 사진, 계정 식별자.
              비밀번호는 받지 않습니다.
            </>,
            <>
              <b>회원이 직접 등록하는 것</b> — 회원이 고른 LLM 제공자의 API 키.{' '}
              <b>암호화해 보관</b>하며 화면에는 끝 네 자리만 보입니다.
            </>,
            <>
              <b>서비스를 쓰는 과정에서</b> — 분석한 영어 원문과 그 결과, 작문 연습에서
              쓴 문장과 채점 결과, 나의 표현에 담은 항목, 1일 사용량.
            </>,
            <>
              <b>오류가 났을 때</b> — 예외 메시지 · 스택 · 요청 경로 · 회원 식별자.
              <b>요청 본문 · 쿠키 · API 키는 보내지 않습니다</b> (6조).
            </>,
          ]}
        />
      </Clause>

      <Clause n={2} title="이용 목적">
        <Items
          items={[
            '학습 기능 제공 — 문장 분석, 작문 연습 채점, 담아 둔 표현 복습',
            '기기 간 기록 동기화',
            '회원 Gemini 한도가 한꺼번에 소진되지 않도록 1일 호출 한도 적용',
            '오류 원인 파악과 수정',
          ]}
        />
        <p>
          <b>광고와 마케팅에 쓰지 않습니다.</b> 제3자에게 판매하지 않습니다.
        </p>
      </Clause>

      <Clause n={3} title="보관 기간과 삭제">
        <Items
          items={[
            <>
              <b>탈퇴하면 즉시 전부 삭제됩니다</b> — 계정, 분석 기록, 연습 기록,
              나의 표현, 사용량, 암호화된 API 키. <b>되돌릴 수 없습니다.</b>
            </>,
            '기록만 지우고 계정을 남기는 것도 계정 메뉴에서 바로 할 수 있습니다.',
            <>
              <b>다만 오류 로그는 예외입니다.</b> 오류 추적 서비스(Sentry)에 남은 기록에는
              회원 식별자가 포함되어 있고, 그곳의 보관 정책에 따라{' '}
              <b>탈퇴 후에도 일정 기간 남을 수 있습니다.</b> 그 기록에는 회원이 입력한
              문장이나 API 키가 들어 있지 않습니다.
            </>,
          ]}
        />
      </Clause>

      <Clause n={4} title="처리위탁과 국외 이전">
        <p>
          서비스는 아래 {TRANSFERS.length}곳에 처리를 위탁하며, 이들의 서버는 국외에
          있습니다. <b>LLM 제공자는 회원이 고른 한 곳만 호출됩니다</b> — 고르지 않은
          곳으로는 아무것도 나가지 않습니다.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-b border-stone-200 text-left text-stone-400 dark:border-stone-800">
                <th className="py-2 pr-3 font-medium">받는 곳</th>
                <th className="py-2 pr-3 font-medium">국가</th>
                <th className="py-2 pr-3 font-medium">보내는 항목</th>
                <th className="py-2 font-medium">목적</th>
              </tr>
            </thead>
            <tbody>
              {TRANSFERS.map((row) => (
                <tr
                  key={row.받는곳}
                  className="border-b border-stone-100 align-top last:border-0 dark:border-stone-800/60"
                >
                  <td className="py-2 pr-3 font-medium text-stone-900 dark:text-stone-100">
                    {row.받는곳}
                  </td>
                  <td className="py-2 pr-3">{row.국가}</td>
                  <td className="py-2 pr-3">{row.항목}</td>
                  <td className="py-2">{row.목적}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          <b>Gemini 무료 등급은 Google 의 서비스 개선에 입력 데이터가 쓰일 수 있습니다.</b>{' '}
          그래서 민감한 내용을 입력하지 않도록 가입 시 안내합니다. 다른 제공자의 처리
          방침은 각 제공자가 정하며, 회원 본인 계정의 약관이 적용됩니다.
        </p>
      </Clause>

      <Clause n={5} title="회원의 권리">
        <Items
          items={[
            <>
              <b>열람</b> — 쌓인 기록은 화면에서 바로 볼 수 있습니다. 계정 메뉴에서 건수도
              확인할 수 있습니다.
            </>,
            <>
              <b>삭제와 탈퇴</b> — 계정 메뉴에서 직접 처리됩니다. 운영자에게 요청할 필요가
              없습니다.
            </>,
            <>
              <b>API 키 삭제</b> — 같은 자리에서 언제든 지울 수 있습니다. 지우면 분석은
              멈추지만 쌓인 기록은 그대로 볼 수 있습니다.
            </>,
            <>그 밖의 문의는 {OPERATOR.연락처} 로 보내 주세요.</>,
          ]}
        />
      </Clause>

      <Clause n={6} title="안전조치">
        <Items
          items={[
            <>
              <b>API 키 암호화</b> — 회원이 등록한 Gemini 키는 암호화해 보관하며, 평문은
              서버 밖으로 나가지 않습니다.
            </>,
            <>
              <b>회원별 분리</b> — 모든 조회와 삭제가 회원 단위로 좁혀지며, 남의 기록
              번호를 넣어도 거부됩니다. 이 분리는 자동 검사로 고정되어 있습니다.
            </>,
            <>
              <b>오류 로그 걸러내기</b> — 오류를 보낼 때 요청 본문 · 쿠키 · API 키 ·
              내부 변수를 <b>전부 지우고</b> 보냅니다. 이것도 자동 검사로 고정되어 있습니다.
            </>,
            <>
              <b>통신 암호화</b> — 모든 통신은 HTTPS 로 이루어집니다.
            </>,
          ]}
        />
      </Clause>

      <Clause n={7} title="개인정보 보호책임자">
        <p>
          개인이 운영하는 서비스로, 운영자가 보호책임자를 겸합니다 —{' '}
          {OPERATOR.이름} ({OPERATOR.연락처}).
        </p>
      </Clause>

      <Clause n={8} title="방침의 변경">
        <p>
          방침이 바뀌면 서비스 화면에 고지합니다. 회원에게 불리한 변경은 시행 7일 전에
          알립니다.
        </p>
      </Clause>
    </Legal>
  )
}
