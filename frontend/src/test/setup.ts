import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

import { resetBoardroomStore } from '../stores/boardroom-store'
import { resetReviewStore } from '../stores/review-store'
import { resetUIStore } from '../stores/ui-store'

afterEach(() => {
  cleanup()
  resetBoardroomStore()
  resetReviewStore()
  resetUIStore()
})
