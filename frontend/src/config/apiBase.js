/**
 * Base URL for the unified FastAPI backend (GeoAI). Used for /api/ui-config and direct fetches.
 *
 * - Explicit VITE_* URL wins (see .env / Docker build args).
 * - `npm run dev`: defaults to http://localhost:8000 (Vite on another port).
 * - Production (e.g. nginx + Caddy): if unset, use `window.location.origin` so https:// and http:// match the page (avoids CORS/mixed content when users open https://localhost while the bundle still said http://localhost).
 */
export function getApiBaseUrl() {
  const fromEnv =
    import.meta.env.VITE_API_BASE_URL ||
    import.meta.env.VITE_APP_API_BASE_URL_DEV ||
    import.meta.env.VITE_APP_API_BASE_URL_PROD;
  const trimmed = fromEnv != null ? String(fromEnv).trim() : '';
  if (trimmed) {
    return trimmed.replace(/\/$/, '');
  }
  if (import.meta.env.DEV) {
    return 'http://localhost:8000';
  }
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin;
  }
  return 'http://localhost:8000';
}
