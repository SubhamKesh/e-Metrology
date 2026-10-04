/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** Production canonical origin, e.g. https://www.example.com (no trailing slash). */
  readonly VITE_SITE_URL?: string;
  /** Optional Google Search Console HTML-tag verification token. */
  readonly VITE_GSC_VERIFICATION?: string;
}
