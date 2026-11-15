// Typed client over the generated OpenAPI schema (schema.d.ts is generated: `npm run gen:api`, do not hand-edit it).
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const TOKEN_KEY = "gigbid.token";
export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
};
export const setToken = (t: string | null) => {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
};

export const api = createClient<paths>({ baseUrl: "" });
api.use({
  onRequest({ request }) {
    const t = getToken();
    if (t) request.headers.set("Authorization", `Bearer ${t}`);
    return request;
  },
});

// Small helper: unwrap {data, error} and throw a readable error.
export async function call<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error !== undefined || !response.ok) {
    const detail = (error as { detail?: unknown })?.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }
  return data as T;
}
