/** 서버가 /api/config 로 알려주기 전에 잠깐 쓰는 값. 서버 값이 단일 출처다. */
const FALLBACK_MAX_CHARS = 1200

/**
 * 이보다 짧으면 분석하지 않는다.
 *
 * 한두 낱말로는 문맥이 없어 번역·구조·총평이 모두 공허해지고,
 * 그 한 번에도 LLM 호출 네 번이 들어간다.
 */
export const MIN_CHARS = 20

interface Props {
  text: string
  maxChars?: number
  loading: boolean
  onTextChange: (text: string) => void
  onSubmit: () => void
  onTooShort: () => void
}

export function InputPanel({
  text,
  loading,
  maxChars = FALLBACK_MAX_CHARS,
  onTextChange,
  onSubmit,
  onTooShort,
}: Props) {
  const trimmed = text.trim()
  const tooLong = text.length > maxChars
  const tooShort = trimmed.length < MIN_CHARS
  const canSubmit = trimmed.length > 0 && !tooLong && !loading

  // 너무 짧을 때는 버튼을 막지 않고 눌리게 둔다. 막아 두면 왜 안 되는지 알 수 없다.
  function submit() {
    if (!canSubmit) return
    if (tooShort) {
      onTooShort()
      return
    }
    onSubmit()
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && canSubmit) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm dark:border-stone-800 dark:bg-stone-900">
      <textarea
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="분석할 영어 문장이나 문단을 붙여넣으세요."
        rows={6}
        spellCheck={false}
        className="w-full resize-y rounded-xl border border-stone-200 bg-stone-50 p-3 font-mono text-[15px] leading-relaxed outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-stone-700 dark:bg-stone-950 dark:focus:ring-indigo-900"
      />

      {/* **난이도 고르는 자리가 여기 있었다.** 분석에서 걷어내고 작문 연습의 예문으로
          옮겼다 (M16) — 바꾸는 것이 설명의 깊이뿐이었고 "깊게" 가 무엇인지 모델도
          우리도 몰랐다 (`08 §1`). 지금 난이도는 표현 풀이 표 안에서 고른다. */}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <span className={`text-xs ${tooLong ? 'text-red-500' : 'text-stone-400'}`}>
          {text.length.toLocaleString()} / {maxChars.toLocaleString()}자
          {tooLong && ' — 너무 깁니다'}
          {!tooLong && tooShort && trimmed.length > 0 && ` — ${MIN_CHARS}자 이상`}
        </span>

        <button
          type="button"
          onClick={submit}
          disabled={!canSubmit}
          className="ml-auto rounded-xl bg-indigo-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-stone-300 dark:disabled:bg-stone-700"
        >
          {loading ? '분석 중…' : '분석하기'}
        </button>
        <kbd className="hidden text-xs text-stone-400 sm:inline">⌘/Ctrl + Enter</kbd>
      </div>
    </section>
  )
}
