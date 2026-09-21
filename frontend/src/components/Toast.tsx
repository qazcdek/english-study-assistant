import { useEffect, useState } from 'react'

/**
 * 잠깐 떴다 사라지는 알림.
 *
 * 입력이 너무 짧다는 정도의 가벼운 안내에 쓴다. 닫기 버튼을 두지 않고 스스로 사라진다.
 * `message` 가 바뀔 때마다 다시 뜨므로, 같은 메시지를 연달아 띄우려면 키를 바꿔 준다.
 */
export function Toast({ message, duration = 2200 }: { message: string | null; duration?: number }) {
  const [shown, setShown] = useState(false)

  useEffect(() => {
    if (!message) return
    setShown(true)
    const timer = setTimeout(() => setShown(false), duration)
    return () => clearTimeout(timer)
  }, [message, duration])

  if (!message) return null

  return (
    <div
      role="status"
      aria-live="polite"
      className={`pointer-events-none fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full bg-stone-900/90 px-4 py-2 text-sm text-white shadow-lg transition-opacity duration-300 dark:bg-stone-100/90 dark:text-stone-900 ${
        shown ? 'opacity-100' : 'opacity-0'
      }`}
    >
      {message}
    </div>
  )
}
