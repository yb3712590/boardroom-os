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
  loadSnapshot: (options?: { background?: boolean }) => Promise<void>
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
  loadSnapshot: async (options) => {
    const background = options?.background === true
    if (!background) {
      set({
        snapshotLoading: true,
        snapshotError: null,
        runtimeProviderLoading: true,
      })
    }

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
        snapshotError: null,
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
              : '加载运行时供应商设置失败。',
        })
      }
    } catch (error) {
      set({
        snapshotError:
          error instanceof Error ? error.message : '加载最新董事会快照失败。',
      })
    } finally {
      if (!background) {
        set({
          snapshotLoading: false,
          runtimeProviderLoading: false,
        })
      }
    }
  },
  setSnapshotError: (value) => set({ snapshotError: value }),
  setRuntimeProviderError: (value) => set({ runtimeProviderError: value }),
}))

export function resetBoardroomStore() {
  useBoardroomStore.setState(boardroomDefaults)
}
