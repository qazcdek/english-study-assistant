import { useEffect, useRef } from 'react'

interface Props {
  /** 열려 있을 때만 그린다. `null` 이면 아무것도 없다. */
  message: string | null
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

/**
 * 되돌릴 수 없는 일을 하기 전에 한 번 더 묻는다.
 *
 * `window.confirm` 을 쓰지 않는다 — 브라우저마다 모양이 다르고, 다크 모드를 따르지
 * 않으며, 긴 한국어 문장이 잘린다. 무엇보다 **무엇이 사라지는지**를 강조할 수 없다.
 *
 * 기본 포커스는 **아니오**다. 엔터를 눌러 지워 버리는 일이 없어야 한다.
 */
export function ConfirmDialog({
  message,
  confirmLabel = '예',
  cancelLabel = '아니오',
  onConfirm,
  onCancel,
}: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (message === null) return
    cancelRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [message, onCancel])

  if (message === null) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/40 p-4"
      onClick={onCancel}
    >
      <div
        // 상자 안을 눌렀다고 닫히면 안 된다.
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-5 shadow-xl dark:border-stone-700 dark:bg-stone-900"
      >
        <p className="text-sm leading-relaxed text-stone-700 dark:text-stone-200">{message}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-stone-200 px-4 py-1.5 text-sm transition hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-lg bg-red-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-red-500"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
