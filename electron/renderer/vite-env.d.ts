/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ISSUES_URL?: string
  readonly VITE_REPORT_ENDPOINT?: string
  readonly VITE_SHOW_PSEUDO_LOCALE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
