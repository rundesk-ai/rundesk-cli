import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

/**
 * Content lives in `docs/` at the repo root, not under `site/src/`.
 *
 * That separation is the point of the layout: `docs/` is plain markdown that
 * renders on GitHub and would survive Starlight being replaced, and `site/` is
 * the build layer that is allowed to be thrown away. Starlight's own
 * `docsLoader()` only looks inside the Astro project, so this uses the glob
 * loader with the same schema to reach one level up.
 */
/**
 * Only the published areas, not everything under `docs/`.
 *
 * `main` also keeps plain repository markdown here — `discord.md`, `configuration.md`,
 * and the adapter contracts under `extending/` — written to be read on GitHub and
 * carrying no frontmatter. A bare `**\/*.md` picks those up and fails the build on a
 * missing title, so the areas the site publishes are named. A page joins an area to be
 * published; it does not appear by being dropped into `docs/`.
 */
const AREAS = '{start,concepts,guides,reference,extend}';

export const collections = {
	docs: defineCollection({
		loader: glob({ pattern: ['index.mdx', `${AREAS}/**/*.{md,mdx}`], base: '../docs' }),
		schema: docsSchema(),
	}),
};
