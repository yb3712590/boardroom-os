import { create } from 'zustand'

import { getDashboard, getInbox, getRuntimeProvider, getWorkforce } from '../api/projections'
import type { DashboardData, InboxData, RuntimeProviderData, WorkforceData } from '../types/api'

type BoardroomState = {
  dashboard: DashboardData | null
  inbox: InboxData | null
  workforce: WorkforceData | null
  runtimeProvider: RuntimeProviderData | null
  snapshotLoading: boolean
  snapshotError: string | null
  runtimeProviderLoading: boolean
  runtimeProviderError: string | null
  loadSnapshot: () => Promise<void>
  setSnapshotError: (value: string | null) => void
  setRuntimeProviderError: (value: string | null) => void
}

const boardroomDefaults = {
  dashboard: null,
  inbox: null,
  workforce: null,
  runtimeProvider: null,
  snapshotLoading: true,
  snapshotError: null,
  runtimeProviderLoading: true,
  runtimeProviderError: null,
}

export const useBoardroomStore = create<BoardroomState>((set) => ({
  ...boardroomDefaults,
  loadSnapshot: async () => {
    set({
      snapshotLoading: true,
      snapshotError: null,
      runtimeProviderLoading: true,
    })

    try {
      const [snapshotResult, runtimeProviderResult] = await Promise.allSettled([
        Promise.all([getDashboard(), getInbox(), getWorkforce()]),
        getRuntimeProvider(),
      ])

      if (snapshotResult.status === 'rejected') {
        throw snapshotResult.reason
      }

      const [dashboard, inbox, workforce] = snapshotResult.value
      set({
        dashboard,
        inbox,
        workforce,
      })

      if (runtimeProviderResult.status === 'fulfilled') {
        set({
          runtimeProvider: runtimeProviderResult.value,
          runtimeProviderError: null,
        })
      } else {
        set({
          runtimeProvider: null,
          runtimeProviderError:
            runtimeProviderResult.reason instanceof Error
              ? runtimeProviderResult.reason.message
              : 'Failed to load runtime provider settings.',
        })
      }
    } catch (error) {
      set({
        snapshotError:
          error instanceof Error ? error.message : 'Failed to load the latest boardroom snapshot.',
      })
    } finally {
      set({
        snapshotLoading: false,
        runtimeProviderLoading: false,
      })
    }
  },
  setSnapshotError: (value) => set({ snapshotError: value }),
  setRuntimeProviderError: (value) => set({ runtimeProviderError: value }),
}))

export function resetBoardroomStore() {
  useBoardroomStore.setState(boardroomDefaults)
}
