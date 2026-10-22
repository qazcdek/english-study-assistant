import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// 테스트마다 DOM 을 비운다. 안 비우면 앞 테스트가 그린 별이 다음 테스트에 잡힌다.
afterEach(cleanup)

// 화면 너비를 바꿔 둔 테스트가 다음 테스트로 새지 않게 한다.
afterEach(() => {
  delete (window as { matchMedia?: unknown }).matchMedia
})
