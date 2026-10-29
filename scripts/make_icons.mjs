// Draw Envoy's icons (Home Screen, manifest, browser tab, notification badge) into web/public/icons/ from one source,
// web/public/icons/mark.svg: the avatar's resting face on a sage tile.
//
//   node scripts/make_icons.mjs
//
// iOS fills transparent pixels with black and rounds the corners itself, so the apple-touch icon is a full square. The
// maskable icon keeps the face inside the safe zone (the middle 80%). Android shows a notification badge in one color,
// so the badge is a white silhouette on transparent with the eyes cut out.
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(ROOT, "web", "public", "icons");
const sharp = createRequire(join(ROOT, "web", "package.json"))("sharp");

const src = readFileSync(join(OUT, "mark.svg"), "utf8");
const face = src.match(/<path d="([^"]+)"/)[1];
const [sage, cream] = [src.match(/<rect[^>]*fill="([^"]+)"/)[1], src.match(/<path[^>]*fill="([^"]+)"/)[1]];

const eyes = (rx, ry, fill) => `<ellipse cx="47" cy="58" rx="${rx}" ry="${ry}" fill="${fill}"/><ellipse cx="73" cy="58" rx="${rx}" ry="${ry}" fill="${fill}"/>`;
const tile = ({ radius = 28, scale = 0.68, rx = 6, ry = 8 } = {}) => {
  const shift = (120 - 120 * scale) / 2;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><rect width="120" height="120" rx="${radius}" fill="${sage}"/>`
    + `<g transform="translate(${shift} ${shift}) scale(${scale})"><path d="${face}" fill="${cream}"/>${eyes(rx, ry, sage)}</g></svg>`;
};
const badge = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 8 100 100"><mask id="m"><rect x="0" y="0" width="120" height="120" fill="#fff"/>${eyes(6.5, 9, "#000")}</mask>`
  + `<path d="${face}" fill="#fff" mask="url(#m)"/></svg>`;

const png = (svg, size, file, opaque = false) => {
  let img = sharp(Buffer.from(svg), { density: Math.ceil((72 * size) / 120) * 4 }).resize(size, size);
  if (opaque) img = img.flatten({ background: sage });
  return img.png().toFile(join(OUT, file));
};

const favicon = tile({ rx: 7, ry: 9 }); // the browser tab: bigger eyes, to read at 16px
writeFileSync(join(OUT, "favicon.svg"), favicon + "\n");
await Promise.all([
  png(tile(), 192, "icon-192.png"),
  png(tile(), 512, "icon-512.png"),
  png(tile({ radius: 0 }), 180, "apple-touch-icon.png", true),
  png(tile({ radius: 0, scale: 0.6 }), 512, "maskable-512.png", true),
  png(favicon, 64, "favicon-64.png"),
  png(badge, 96, "badge-96.png"),
]);
console.log("icons in", OUT);
