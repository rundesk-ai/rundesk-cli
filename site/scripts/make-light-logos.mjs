/**
 * Derive the light-theme logotypes from the dark ones.
 *
 * The shipped marks carry white letterforms and a red glyph. White letterforms
 * vanish on a white page, and a CSS filter cannot recolour one without also
 * recolouring the other — so the letterforms are repainted here and the red is
 * left exactly as it is.
 *
 * Run after replacing a source mark: `node scripts/make-light-logos.mjs`.
 */
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import sharp from 'sharp';

const assets = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'assets');

/** `--sl-color-white` under `[data-theme='light']` — the ink the rest of the page uses. */
const INK = { r: 0x0b, g: 0x0f, b: 0x1e };

/**
 * A letterform pixel is bright and close to neutral. Testing saturation rather
 * than brightness alone is what keeps the red glyph out of the repaint: its
 * lightest antialiased edges are bright too.
 */
function letterform(r, g, b) {
	const high = Math.max(r, g, b);
	const low = Math.min(r, g, b);
	return high > 110 && high - low < 40;
}

for (const name of ['rundesk-wordmark', 'rundesk-lockup']) {
	const source = join(assets, `${name}.png`);
	const { data, info } = await sharp(source).ensureAlpha().raw().toBuffer({ resolveWithObject: true });

	for (let i = 0; i < data.length; i += info.channels) {
		if (data[i + 3] === 0) continue;
		if (!letterform(data[i], data[i + 1], data[i + 2])) continue;
		data[i] = INK.r;
		data[i + 1] = INK.g;
		data[i + 2] = INK.b;
	}

	const target = join(assets, `${name}-light.png`);
	await sharp(data, { raw: { width: info.width, height: info.height, channels: info.channels } })
		.png()
		.toFile(target);
	console.log(`make-light-logos: wrote ${name}-light.png`);
}
