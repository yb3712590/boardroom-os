import { create } from 'zustand'

import { getDeveloperInspector, getReviewRoom } from '../api/projections'
import type { DeveloperInspectorData, ReviewRoomData } from '../types/api'

type ReviewState = {
  reviewRoom: ReviewRoomData | null
  developerInspector: DeveloperInspectorData | null
  loading: boolean
  inspectorLoading: boolean
  error: string | null
  submittingAction: string | null
  loadReviewRoom: (reviewPackId: string, options?: { background?: boolean }) => Promise<void>
  loadDeveloperInspector: (reviewPackId: string) => Promise<void>
  clearReview: () => void
  setSubmittingAction: (value: string | null) => void
  setError: (value: string | null) => void
}

const reviewDefaults = {
  reviewRoom: null,
  developerInspector: null,
  loading: false,
  inspectorLoading: false,
  error: null,
  submittingAction: null,
}

export const useReviewStore = create<ReviewState>((set) => ({
  ...reviewDefaults,
  loadReviewRoom: async (reviewPackId, options) => {
    const background = options?.background === true
    if (!background) {
      set({
        loading: true,
        error: null,
        developerInspector: null,
      })
    }

    try {
      const reviewRoom = await getReviewRoom(reviewPackId)
      set({
        reviewRoom,
        error: null,
      })
    } catch (error) {
      if (background) {
        return
      }
      set({
        error: error instanceof Error ? error.message : '加载当前评审包失败。',
        reviewRoom: null,
      })
    } finally {
      if (!background) {
        set({ loading: false })
      }
    }
  },
  loadDeveloperInspector: async (reviewPackId) => {
    set({
      inspectorLoading: true,
      error: null,
    })

    try {
      const developerInspector = await getDeveloperInspector(reviewPackId)
      set({ developerInspector })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : '加载开发者检查器失败。',
      })
    } finally {
      set({ inspectorLoading: false })
    }
  },
  clearReview: () =>
    set({
      ...reviewDefaults,
    }),
  setSubmittingAction: (value) => set({ submittingAction: value }),
  setError: (value) => set({ error: value }),
}))

export function resetReviewStore() {
  useReviewStore.setState(reviewDefaults)
}
