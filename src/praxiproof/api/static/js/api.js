// Fetch wrapper shared by every view: JSON-or-text decoding, error surfacing, and the optional API token.
let tokenPrompt = null;
// The server can require an API token (PRAXIPROOF_API_TOKEN). It is kept in a cookie so <video> and <img> requests carry it too.
function askForToken() {
  tokenPrompt ??= Promise.resolve().then(() => {
    const value = (window.prompt(t("auth.prompt")) || "").trim();
    tokenPrompt = null;
    if (value) document.cookie = `pp_token=${value}; path=/; SameSite=Strict`;
    return Boolean(value);
  });
  return tokenPrompt;
}

async function api(path, options = {}, retried = false) {
  const response = await fetch(path, options);
  if (response.status === 401 && !retried && (await askForToken())) return api(path, options, true);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const type = response.headers.get("content-type") || "";
  return type.includes("json") ? response.json() : response.text();
}

// A page renderer awaits several GETs; if the user has navigated on by the time one returns, drop the whole render
// instead of letting it overwrite the newer page (Settings waits ~1s on /api/models and used to clobber the next view).
function rapi(path) {
  const token = state.renderToken;
  return api(path).then((result) => {
    if (token !== state.renderToken) throw STALE;
    return result;
  });
}
