import type { HistoryEntry } from '../lib/history'

function TrashIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  )
}

interface Props {
  entries: HistoryEntry[]
  activeId: string | null
  onSelect: (entry: HistoryEntry) => void
  onDelete: (entry: HistoryEntry) => void
}

export function HistoryList({ entries, activeId, onSelect, onDelete }: Props) {
  if (entries.length === 0) {
    return (
      <p className="px-2 text-xs leading-relaxed text-stone-400">
        분석한 문장이 여기에 쌓입니다.
      </p>
    )
  }

  return (
    <ul className="flex flex-col gap-1">
      {entries.map((entry) => {
        const active = entry.id === activeId
        return (
          // 삭제 버튼을 목록 버튼 안에 넣을 수 없어(버튼 중첩 금지) 형제로 두고 겹친다.
          <li key={entry.id} className="group relative">
            <button
              type="button"
              onClick={() => onSelect(entry)}
              className={`w-full truncate rounded-lg py-2 pl-2.5 pr-8 text-left text-xs transition ${
                active
                  ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'
                  : 'text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800'
              }`}
              title={entry.text}
            >
              {entry.text}
            </button>

            <button
              type="button"
              onClick={() => onDelete(entry)}
              aria-label={`삭제: ${entry.text.slice(0, 40)}`}
              title="삭제"
              className={`absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-stone-400 transition
                opacity-0 group-hover:opacity-100 focus-visible:opacity-100
                hover:bg-red-100 hover:text-red-600
                dark:hover:bg-red-950/60 dark:hover:text-red-400 ${
                  active ? 'hover:bg-red-100 dark:hover:bg-red-950/60' : ''
                }`}
            >
              <TrashIcon />
            </button>
          </li>
        )
      })}
    </ul>
  )
}
