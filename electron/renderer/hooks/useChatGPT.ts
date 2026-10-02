import { useSyncExternalStore } from 'react'
import type { ChatGPTResult, ChatGPTStatus } from '../global'

// Every surface observes one account/selection, including while an IPC save is
// finishing. Catalog discovery is shared rather than repeated by hidden tabs.
let snapshot = { status: null as ChatGPTStatus | null, modelsLoading: false, modelSaving: false,
  catalogError: null as string | null, modelRevision: 0 }
const listeners = new Set<() => void>()
let cleanup: (() => void) | undefined
let catalogRequest: Promise<ChatGPTResult | null> | null = null
let selectionRequest: Promise<ChatGPTResult | null> | null = null
function update(patch: Partial<typeof snapshot>) {
  snapshot = { ...snapshot, ...patch }
  for (const listener of listeners) listener()
}
function setStatus(status: ChatGPTStatus) {
  const changedAccount = snapshot.status?.account?.id !== status.account?.id
  update({ status, ...(changedAccount ? { catalogError: null } : {}) })
}
function accept(result: ChatGPTResult) { setStatus(result.status); return result }
async function reload() {
  const result = await window.electronAPI?.chatgpt.status()
  if (result?.ok) accept(result)
}
function subscribe(listener: () => void) {
  listeners.add(listener)
  if (listeners.size === 1) {
    cleanup = window.electronAPI?.chatgpt.onChanged(setStatus)
    void reload().catch(() => {})
  }
  return () => {
    listeners.delete(listener)
    if (!listeners.size) { cleanup?.(); cleanup = undefined }
  }
}
async function loadModels() {
  if (catalogRequest) return catalogRequest
  update({ modelsLoading: true, catalogError: null })
  catalogRequest = (async () => {
    try {
      const result = await window.electronAPI?.chatgpt.models()
      if (!result) throw new Error('unavailable')
      accept(result)
      if (!result.ok) update({ catalogError: result.code || 'CHATGPT_UNAVAILABLE' })
      return result
    } catch { update({ catalogError: 'CHATGPT_UNAVAILABLE' }); return null }
    finally { catalogRequest = null; update({ modelsLoading: false }) }
  })()
  return catalogRequest
}
async function selectModel(model: string) {
  if (selectionRequest) return null
  update({ modelSaving: true })
  selectionRequest = (async () => {
    try {
      const result = await window.electronAPI?.chatgpt.selectModel(model)
      if (!result) throw new Error('unavailable')
      accept(result)
      // IPC resolves after the main process persists the provider settings.
      // Settings can now reload its baseline without overwriting other drafts.
      if (result.ok) update({ modelRevision: snapshot.modelRevision + 1, catalogError: null })
      return result
    } catch { return null }
    finally { selectionRequest = null; update({ modelSaving: false }) }
  })()
  return selectionRequest
}
const getSnapshot = () => snapshot
export function useChatGPT() {
  return { ...useSyncExternalStore(subscribe, getSnapshot), reload, accept, loadModels, selectModel }
}

export const manageChatGPTUsage = () => window.electronAPI?.openExternal('https://chatgpt.com/settings/usage')
