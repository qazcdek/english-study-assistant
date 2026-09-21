import type { Level } from '../lib/types'

const LEVELS: { value: Level; label: string }[] = [
  { value: 'beginner', label: '초급' },
  { value: 'intermediate', label: '중급' },
  { value: 'advanced', label: '상급' },
]

// backend/app/schemas.py 의 MAX_INPUT_CHARS 와 같아야 한다.
const MAX_CHARS = 2000

/**
 * 이보다 짧으면 분석하지 않는다.
 *
 * 한두 낱말로는 문맥이 없어 번역·구조·총평이 모두 공허해지고,
 * 그 한 번에도 LLM 호출 네 번이 들어간다.
 */
export const MIN_CHARS = 20

interface Props {
  text: string
  level: Level
  loading: boolean
  onTextChange: (text: string) => void
  onLevelChange: (level: Level) => void
  onSubmit: () => void
  onTooShort: () => void
}

export function InputPanel({
  text,
  level,
  loading,
  onTextChange,
  onLevelChange,
  onSubmit,
  onTooShort,
}: Props) {
  const trimmed = text.trim()
  const tooLong = text.length > MAX_CHARS
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

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 rounded-lg bg-stone-100 p-1 dark:bg-stone-800">
          {LEVELS.map((l) => (
            <button
              key={l.value}
              type="button"
              onClick={() => onLevelChange(l.value)}
              className={`rounded-md px-3 py-1 text-sm transition ${
                level === l.value
                  ? 'bg-white font-medium text-indigo-600 shadow-sm dark:bg-stone-700 dark:text-indigo-300'
                  : 'text-stone-500 hover:text-stone-800 dark:hover:text-stone-200'
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>

        <span className={`text-xs ${tooLong ? 'text-red-500' : 'text-stone-400'}`}>
          {text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}자
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
