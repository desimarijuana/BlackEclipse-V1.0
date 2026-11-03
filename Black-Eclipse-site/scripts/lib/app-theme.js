// Read the user's APP-WIDE theme for the desktop progress page.
//
// The theme lives in JDDS (`SystemConfig`, key `eclipse_theme`) as plain JSON,
// written by Settings › Customization via `/api/theme` (src/lib/theme/server.ts).
// It is app-wide on purpose, so every origin and device renders the same look —
// including this page, which is served from a different origin (127.0.0.1) and
// can therefore never read the app's `localStorage`.
//
// The launcher only reads, with a short-lived read-only connection. Any failure
// (module missing, DB locked, malformed row) falls back to the shipped theme, so
// a customization can never stop the app from starting.
//
// Everything below is sanitized before it reaches CSS/HTML: the row is user
// data, and this page must never let it inject markup or a stylesheet break.

const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const DB_FILE = path.join(ROOT, "jdds.db");
const PUBLIC_DIR = path.join(ROOT, "public");
const THEME_KEY = "eclipse_theme";

// Mirrors DEFAULT_ECLIPSE_THEME in src/lib/theme/tokens.ts. Kept as plain data
// so the launcher never has to import TypeScript or the React bundle.
const DEFAULT_THEME = {
  appName: "BlackEclipse",
  logoText: "",
  logoUrl: "",
  faviconUrl: "",
  fontUi: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  fontMono: '"JetBrains Mono", "IBM Plex Mono", "SF Mono", Consolas, monospace',
  colors: {
    primary: "#7aff78",
    accent: "#34d399",
    background: "#000000",
    surface: "#0f0f0f",
    border: "#2a2a2e",
    text: "#f4f4f5",
  },
  radius: 0.6,
  logoScale: 1,
  glass: { enabled: true, blur: 18, opacity: 0.55, tint: "#121214" },
  shadow: "soft",
  background: "solid",
  scheme: "dark",
  glow: true,
  animations: true,
};

const HEX_RE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
const SCHEMES = new Set(["dark", "light"]);
const SHADOWS = new Set(["none", "soft", "medium", "dramatic"]);
const BACKGROUNDS = new Set(["solid", "gradient", "grid"]);

function hex(value, fallback) {
  if (typeof value !== "string") return fallback;
  const raw = value.trim();
  if (!HEX_RE.test(raw)) return fallback;
  const v = raw.toLowerCase();
  return v.length === 4 ? `#${v[1]}${v[1]}${v[2]}${v[2]}${v[3]}${v[3]}` : v;
}

function triplet(value) {
  const v = hex(value, "#000000");
  return `${parseInt(v.slice(1, 3), 16)} ${parseInt(v.slice(3, 5), 16)} ${parseInt(v.slice(5, 7), 16)}`;
}

function clampNumber(value, fallback, min, max) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

// Font stacks are CSS values, not free text: keep only the characters those
// stacks actually use, and cap the length. This blocks `</style>` / `url(...)`
// style injection from a hand-edited settings row.
function fontStack(value, fallback) {
  if (typeof value !== "string") return fallback;
  const clean = value.replace(/[^a-zA-Z0-9 ,"'-]/g, "").trim().slice(0, 160);
  return clean || fallback;
}

function appName(value) {
  if (typeof value !== "string") return DEFAULT_THEME.appName;
  const clean = value.replace(/[<>]/g, "").trim().slice(0, 60);
  return clean || DEFAULT_THEME.appName;
}

/**
 * A theme image is either an inline data URL (uploaded logo) or a path inside
 * `public/`. Remote http(s) URLs are rejected: the boot page must paint without
 * a network round-trip, and it must not leak a request to a third party.
 */
function imageRef(value) {
  if (typeof value !== "string") return "";
  const raw = value.trim();
  if (raw.length > 4 * 1024 * 1024) return "";
  if (/^data:image\/(svg\+xml|png|jpeg|jpg|webp|gif);base64,/i.test(raw)) return raw;
  if (raw.startsWith("/") && !raw.includes("..") && !raw.includes("//")) return raw;
  return "";
}

/** Normalize a raw theme row into the small shape the splash page renders. */
function sanitizeTheme(raw) {
  const input = raw && typeof raw === "object" ? raw : {};
  const colors = input.colors && typeof input.colors === "object" ? input.colors : {};
  const glass = input.glass && typeof input.glass === "object" ? input.glass : {};
  const scheme = SCHEMES.has(input.scheme) ? input.scheme : DEFAULT_THEME.scheme;
  const base = DEFAULT_THEME.colors;

  return {
    appName: appName(input.appName),
    logoText: typeof input.logoText === "string" ? input.logoText.replace(/[<>]/g, "").slice(0, 8) : "",
    logoUrl: imageRef(input.logoUrl),
    faviconUrl: imageRef(input.faviconUrl),
    fontUi: fontStack(input.fontUi, DEFAULT_THEME.fontUi),
    fontMono: fontStack(input.fontMono, DEFAULT_THEME.fontMono),
    scheme,
    colors: {
      primary: hex(colors.primary, base.primary),
      accent: hex(colors.accent, base.accent),
      background: hex(colors.background, base.background),
      surface: hex(colors.surface, base.surface),
      border: hex(colors.border, base.border),
      text: hex(colors.text, base.text),
    },
    primaryRgb: triplet(hex(colors.primary, base.primary)),
    accentRgb: triplet(hex(colors.accent, base.accent)),
    surfaceRgb: triplet(hex(colors.surface, base.surface)),
    textRgb: triplet(hex(colors.text, base.text)),
    radius: clampNumber(input.radius, DEFAULT_THEME.radius, 0, 2),
    logoScale: clampNumber(input.logoScale, DEFAULT_THEME.logoScale, 0.5, 2),
    glass: {
      enabled: glass.enabled !== false,
      blur: clampNumber(glass.blur, DEFAULT_THEME.glass.blur, 0, 60),
      opacity: clampNumber(glass.opacity, DEFAULT_THEME.glass.opacity, 0.15, 0.95),
      tint: hex(glass.tint, DEFAULT_THEME.glass.tint),
    },
    shadow: SHADOWS.has(input.shadow) ? input.shadow : DEFAULT_THEME.shadow,
    background: BACKGROUNDS.has(input.background) ? input.background : DEFAULT_THEME.background,
    glow: input.glow !== false,
    animations: input.animations !== false,
    source: "db",
  };
}

function fallbackTheme() {
  return { ...sanitizeTheme(DEFAULT_THEME), source: "default" };
}

/** Read the saved theme. Never throws. */
function readTheme() {
  let Database;
  try {
    Database = require("better-sqlite3");
  } catch {
    return fallbackTheme();
  }
  let db;
  try {
    db = new Database(DB_FILE, { readonly: true, fileMustExist: true });
    const row = db.prepare("SELECT value FROM SystemConfig WHERE key = ?").get(THEME_KEY);
    if (!row || !row.value || row.value === "null") return fallbackTheme();
    return sanitizeTheme(JSON.parse(row.value));
  } catch {
    return fallbackTheme();
  } finally {
    try {
      db && db.close();
    } catch {
      /* best effort */
    }
  }
}

/**
 * Resolve a sanitized image reference to bytes for the splash server.
 * Returns `{ data, contentType }` or null when the caller should use the
 * shipped brand file instead.
 */
function imageBytes(ref) {
  if (!ref) return null;
  const data = /^data:(image\/[a-z+]+);base64,(.+)$/i.exec(ref);
  if (data) {
    try {
      return { data: Buffer.from(data[2], "base64"), contentType: data[1] };
    } catch {
      return null;
    }
  }
  if (ref.startsWith("/")) {
    const file = path.resolve(PUBLIC_DIR, `.${ref}`);
    // Never escape public/ through a crafted path.
    if (!file.startsWith(PUBLIC_DIR + path.sep)) return null;
    try {
      const ext = path.extname(file).toLowerCase();
      const type =
        ext === ".svg"
          ? "image/svg+xml"
          : ext === ".png"
            ? "image/png"
            : ext === ".jpg" || ext === ".jpeg"
              ? "image/jpeg"
              : ext === ".webp"
                ? "image/webp"
                : ext === ".gif"
                  ? "image/gif"
                  : null;
      if (!type) return null;
      return { data: require("fs").readFileSync(file), contentType: type };
    } catch {
      return null;
    }
  }
  return null;
}

module.exports = { readTheme, sanitizeTheme, imageBytes, DEFAULT_THEME, THEME_KEY };
