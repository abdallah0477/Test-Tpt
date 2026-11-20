/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** noVNC page of the Runner's visible browser. */
  readonly VITE_NOVNC_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
