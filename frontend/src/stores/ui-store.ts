import { create } from 'zustand'

type UIState = {
  dependencyInspectorOpen: boolean
  providerSettingsOpen: boolean
  projectInitPending: boolean
  submittingStaffingAction: string | null
  submittingIncidentAction: boolean
  runtimeProviderSubmitting: boolean
  setDependencyInspectorOpen: (value: boolean) => void
  setProviderSettingsOpen: (value: boolean) => void
  setProjectInitPending: (value: boolean) => void
  setSubmittingStaffingAction: (value: string | null) => void
  setSubmittingIncidentAction: (value: boolean) => void
  setRuntimeProviderSubmitting: (value: boolean) => void
}

const uiDefaults = {
  dependencyInspectorOpen: false,
  providerSettingsOpen: false,
  projectInitPending: false,
  submittingStaffingAction: null,
  submittingIncidentAction: false,
  runtimeProviderSubmitting: false,
}

export const useUIStore = create<UIState>((set) => ({
  ...uiDefaults,
  setDependencyInspectorOpen: (value) => set({ dependencyInspectorOpen: value }),
  setProviderSettingsOpen: (value) => set({ providerSettingsOpen: value }),
  setProjectInitPending: (value) => set({ projectInitPending: value }),
  setSubmittingStaffingAction: (value) => set({ submittingStaffingAction: value }),
  setSubmittingIncidentAction: (value) => set({ submittingIncidentAction: value }),
  setRuntimeProviderSubmitting: (value) => set({ runtimeProviderSubmitting: value }),
}))

export function resetUIStore() {
  useUIStore.setState(uiDefaults)
}
