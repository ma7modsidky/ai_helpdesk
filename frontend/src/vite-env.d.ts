/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Base URL of the API. Empty by default, which means same-origin: the Vite dev
   * server proxies `/api` locally and the container proxies it in deployment, so no
   * CORS configuration exists (ADR-030). This is the only build-time variable, and it
   * is not a secret.
   */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
