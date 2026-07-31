/**
 * Compose the social card served as `og:image`.
 *
 * A link to these docs pasted into Discord — which is the channel Rundesk ships
 * first-class — renders as a bare text row without one, because Starlight declares
 * `twitter:card=summary_large_image` and had no image to put in it.
 *
 * Run after replacing a source mark: `node scripts/make-social-card.mjs`. The result
 * is committed, so nothing has to render text at build time on a machine whose fonts
 * are not ours.
 */
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readFile } from 'node:fs/promises';
import sharp from 'sharp';

const here = dirname(fileURLToPath(import.meta.url));
const site = join(here, '..');

const WIDTH = 1200;
const HEIGHT = 630;
const GROUND = '#010515';

const wordmark = await sharp(join(site, 'src', 'assets', 'rundesk-wordmark.png'))
	.resize({ width: 620 })
	.toBuffer();

const mono = await readFile(join(site, 'public', 'fonts', 'plex-mono-500.woff2'));

/* The tagline is drawn as SVG text with the face embedded as a data URI, so the
   render does not depend on what is installed on the machine doing it. */
const overlay = Buffer.from(`
<svg width="${WIDTH}" height="${HEIGHT}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      @font-face {
        font-family: 'Plex Mono';
        src: url('data:font/woff2;base64,${mono.toString('base64')}') format('woff2');
      }
      .tag { font-family: 'Plex Mono', monospace; font-size: 27px; fill: #8a90a6; letter-spacing: 0.5px; }
      .host { font-family: 'Plex Mono', monospace; font-size: 23px; fill: #fd3031; font-weight: 500; }
    </style>
    <radialGradient id="bloom" cx="0.82" cy="0" r="0.75">
      <stop offset="0%" stop-color="#fd3031" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="#fd3031" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="${WIDTH}" height="${HEIGHT}" fill="${GROUND}"/>
  <rect width="${WIDTH}" height="${HEIGHT}" fill="url(#bloom)"/>
  <text class="tag" x="90" y="410">Run the coding CLI you already use as a</text>
  <text class="tag" x="90" y="450">durable, named teammate on your own Mac.</text>
  <text class="host" x="90" y="545">docs.rundesk.ai</text>
  <rect x="0" y="${HEIGHT - 6}" width="${WIDTH}" height="6" fill="#fd3031"/>
</svg>`);

await sharp({
	create: { width: WIDTH, height: HEIGHT, channels: 4, background: GROUND },
})
	.composite([
		{ input: overlay, top: 0, left: 0 },
		{ input: wordmark, top: 210, left: 90 },
	])
	.png()
	.toFile(join(site, 'public', 'og.png'));

console.log('make-social-card: wrote public/og.png');
