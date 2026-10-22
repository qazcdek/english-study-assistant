import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'

const countDuplicates = vi.fn<() => Promise<{ removed: number }>>()
const tidyHistory = vi.fn<() => Promise<{ removed: number }>>()

vi.mock('../lib/api', () => ({
  countDuplicates: () => countDuplicates(),
  tidyHistory: () => tidyHistory(),
  ApiError: class ApiError extends Error {},
}))

const { TidyButton, TIDY_WARNING } = await import('../components/TidyButton')

beforeEach(() => {
  countDuplicates.mockReset()
  tidyHistory.mockReset()
  tidyHistory.mockResolvedValue({ removed: 2 })
})

test('지울 것이 있으면 무엇이 사라지는지 말하고 묻는다', async () => {
  countDuplicates.mockResolvedValue({ removed: 2 })
  render(<TidyButton onTidied={() => {}} />)

  fireEvent.click(screen.getByText('기록 정리'))

  expect(await screen.findByText(TIDY_WARNING)).toBeTruthy()
  // 묻는 중에는 아직 아무것도 지우지 않는다.
  expect(tidyHistory).not.toHaveBeenCalled()
})

test('경고가 무엇이 남는지 말한다', () => {
  expect(TIDY_WARNING).toContain('최신 기록만 남습니다')
  expect(TIDY_WARNING).toContain('정리하시겠습니까')
})

test('예 를 누르면 정리하고 건수를 알려준다', async () => {
  countDuplicates.mockResolvedValue({ removed: 2 })
  const told: number[] = []
  render(<TidyButton onTidied={(n) => told.push(n)} />)

  fireEvent.click(screen.getByText('기록 정리'))
  fireEvent.click(await screen.findByText('예'))

  await waitFor(() => expect(told).toEqual([2]))
})

test('아니오 를 누르면 아무 일도 없다', async () => {
  countDuplicates.mockResolvedValue({ removed: 2 })
  render(<TidyButton onTidied={() => {}} />)

  fireEvent.click(screen.getByText('기록 정리'))
  fireEvent.click(await screen.findByText('아니오'))

  expect(tidyHistory).not.toHaveBeenCalled()
  expect(screen.queryByText(TIDY_WARNING)).toBeNull()
})

test('지울 것이 없으면 묻지 않는다', async () => {
  // **물을 일이 없는데 물으면 다음에 진짜 물을 때 안 읽는다.**
  countDuplicates.mockResolvedValue({ removed: 0 })
  const told: number[] = []
  render(<TidyButton onTidied={(n) => told.push(n)} />)

  fireEvent.click(screen.getByText('기록 정리'))

  await waitFor(() => expect(told).toEqual([0]))
  expect(screen.queryByText(TIDY_WARNING)).toBeNull()
  expect(tidyHistory).not.toHaveBeenCalled()
})

test('묻기 전에 먼저 세어 본다', async () => {
  // 세지 않고 물으면 "0건 정리했습니다" 를 보여주게 된다.
  countDuplicates.mockResolvedValue({ removed: 3 })
  render(<TidyButton onTidied={() => {}} />)

  fireEvent.click(screen.getByText('기록 정리'))

  await waitFor(() => expect(countDuplicates).toHaveBeenCalledTimes(1))
})
