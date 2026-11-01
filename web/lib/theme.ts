// Light or dark (Settings › Appearance), per device: Light (the default, whatever the device's setting), Dark, or Match
// device. The choice lives in this browser's localStorage. `THEME_SCRIPT` runs in <head> before the first paint (no cream
// flash on a dark visit): it sets data-theme on <html>, which picks globals.css's dark tokens, points the browser's
// theme-color at the page's color, and while the choice is Match device follows the device as it changes. Anything that
// draws with the tokens itself (the memory graph's canvas) watches data-theme.

export type ThemeChoice = "light" | "dark" | "system";
const KEY = "envoy-theme";

export const THEME_SCRIPT = `(function () {
  var K = ${JSON.stringify(KEY)}, q = window.matchMedia("(prefers-color-scheme: dark)"), kept = null;
  function apply(choice) {
    if (typeof choice === "string") kept = choice;  // remembered for this visit, if storage is off (private mode)
    var c = kept;
    try { c = localStorage.getItem(K) || kept; } catch (e) {}
    var dark = c === "dark" || (c === "system" && q.matches), root = document.documentElement;
    if (dark) root.dataset.theme = "dark"; else delete root.dataset.theme;
    var m = document.querySelector('meta[name="theme-color"]');
    if (m) m.content = dark ? "#121815" : "#ece7dc";
  }
  apply();
  document.addEventListener("DOMContentLoaded", function () { apply(); });  // the theme-color tag may come after this script
  q.addEventListener("change", function () { apply(); });
  window.addEventListener("storage", function (e) { if (e.key === K) apply(); });
  window.__envoyTheme = apply;
})();`;

export function themeChoice(): ThemeChoice {
  let c: string | null = null;
  try { c = localStorage.getItem(KEY); } catch { /* private mode */ }
  c ??= document.documentElement.dataset.theme === "dark" ? "dark" : null;
  return c === "dark" || c === "system" ? c : "light";
}

export function setThemeChoice(c: ThemeChoice): void {
  try { localStorage.setItem(KEY, c); } catch { /* private mode: this visit only */ }
  (window as unknown as { __envoyTheme?: (c: ThemeChoice) => void }).__envoyTheme?.(c);
}
