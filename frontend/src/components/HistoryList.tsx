import type { HistoryEntry } from '../lib/history'

interface Props {
  entries: HistoryEntry[]
  activeId: string | null
  onSelect: (entry: HistoryEntry) => void
}

export function HistoryList({ entries, activeId, onSelect }: Props) {
  if (entries.length === 0) {
    return (
      <p className="px-2 text-xs leading-relaxed text-stone-400">
        분석한 문장이 여기에 쌓입니다. 브라우저에만 저장됩니다.
      </p>
    )
  }

  return (
    <ul className="flex flex-col gap-1">
      {entries.map((entry) => (
        <li key={entry.id}>
          <button
            type="button"
            onClick={() => onSelect(entry)}
            className={`w-full truncate rounded-lg px-2.5 py-2 text-left text-xs transition ${
              entry.id === activeId
                ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'
                : 'text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800'
            }`}
            title={entry.text}
          >
            {entry.text}
          </button>
        </li>
      ))}
    </ul>
  )
}
