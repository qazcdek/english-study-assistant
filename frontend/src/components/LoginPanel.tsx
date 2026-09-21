import { loginUrl } from '../lib/api'

export function LoginPanel({ error }: { error?: string | null }) {
  return (
    <div className="mx-auto max-w-md rounded-2xl border border-stone-200 bg-white p-8 text-center shadow-sm dark:border-stone-800 dark:bg-stone-900">
      <h2 className="text-lg font-semibold tracking-tight">English Study Assistant</h2>
      <p className="mt-2 text-sm leading-relaxed text-stone-500 dark:text-stone-400">
        영어 문장을 번역 · 표현 풀이 · 문장 구조 · 총평으로 정리하고,
        <br />
        예문을 직접 써 보며 연습합니다.
      </p>

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 p-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
          로그인에 실패했습니다: {error}
        </p>
      )}

      <a
        href={loginUrl('/')}
        className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-stone-300 bg-white py-2.5 text-sm font-medium text-stone-700 transition hover:bg-stone-50 dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100 dark:hover:bg-stone-700"
      >
        <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
          <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.6 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6.1C12.3 13.2 17.6 9.5 24 9.5z" />
          <path fill="#4285F4" d="M46.9 24.5c0-1.6-.1-3.2-.4-4.7H24v9h12.9c-.6 3-2.3 5.6-4.9 7.3l7.6 5.9c4.4-4.1 7.3-10.2 7.3-17.5z" />
          <path fill="#FBBC05" d="M10.4 28.7a14.5 14.5 0 0 1 0-9.4l-7.8-6.1a24 24 0 0 0 0 21.6l7.8-6.1z" />
          <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.6-5.9c-2.1 1.4-4.9 2.3-8.3 2.3-6.4 0-11.7-3.7-13.6-9.1l-7.8 6.1C6.5 42.6 14.6 48 24 48z" />
        </svg>
        Google 계정으로 시작하기
      </a>

      <p className="mt-4 text-xs leading-relaxed text-stone-400">
        로그인은 신원 확인에만 사용합니다. 분석은 가입 후 등록하시는
        <br />
        회원님의 Gemini API 키로, 회원님의 사용 한도 안에서 이루어집니다.
      </p>
    </div>
  )
}
