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
export const collections = {
	docs: defineCollection({
		loader: glob({ pattern: '**/*.md', base: '../docs' }),
		schema: docsSchema(),
	}),
};
