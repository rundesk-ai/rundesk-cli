// @ts-check
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import starlight from '@astrojs/starlight';
import starlightSidebarTopics from 'starlight-sidebar-topics';

/**
 * Pages live in `../docs`, which has no `node_modules` above it, so a bare
 * `@astrojs/starlight/components` import from a page cannot resolve on its own.
 * Pointing the specifier at this project's copy is what lets content sit outside
 * the Astro project without each page reaching back into `site/` by path.
 */
const require = createRequire(import.meta.url);
const starlightComponents = require.resolve('@astrojs/starlight/components');

// https://astro.build/config
export default defineConfig({
	site: 'https://docs.rundesk.ai',
	vite: {
		resolve: {
			// Exact match only. A bare string alias is a prefix match, and it would
			// also swallow Starlight's own `components/<Name>.astro` imports.
			alias: [
				{
					find: /^@astrojs\/starlight\/components$/,
					replacement: starlightComponents,
				},
				// Lets a page in `../docs` import this project's own components without
				// spelling out a relative path back into `site/`.
				{ find: '@site', replacement: fileURLToPath(new URL('./src', import.meta.url)) },
			],
		},
	},
	integrations: [
		starlight({
			title: 'Rundesk',
			description:
				'Run AI coding agents as durable, named teammates on your own Mac — then reach them from your terminal, Discord, or a schedule.',
			tagline: 'Teammates that remember, adapt, and grow.',
			logo: {
				// The lockup cut out of the repository banner, so the header carries the
				// real letterforms rather than a webfont chosen to look near enough.
				src: './src/assets/rundesk-lockup.png',
				alt: 'Rundesk',
				replacesTitle: true,
			},
			favicon: '/favicon.png',
			customCss: ['./src/styles/brand.css'],
			social: [
				{
					icon: 'github',
					label: 'GitHub',
					href: 'https://github.com/rundesk-ai/rundesk-cli',
				},
			],
			editLink: {
				// Pages resolve as `../docs/<path>` from this project, so the base has to
				// point one level deeper than the repo root for the `..` to land on `main/`.
				baseUrl: 'https://github.com/rundesk-ai/rundesk-cli/edit/main/site/',
			},
			lastUpdated: true,
			pagination: true,
			components: {
				Header: './src/components/Header.astro',
				PageTitle: './src/components/PageTitle.astro',
			},
			plugins: [
				/**
				 * One sidebar per area rather than one long list of everything.
				 * `/` stays an overview with no sidebar; entering an area swaps the
				 * left panel to that area alone.
				 */
				starlightSidebarTopics([
					{
						label: 'Start here',
						link: '/start/what-rundesk-is/',
						items: [
							{
								label: 'First steps',
								items: [
									{ label: 'What Rundesk is', slug: 'start/what-rundesk-is' },
									{ label: 'Install', slug: 'start/install' },
									{ label: 'Your first agent', slug: 'start/first-agent' },
								],
							},
						],
					},
					{
						label: 'Concepts',
						link: '/concepts/agents/',
						items: [
							{
								label: 'How Rundesk works',
								items: [
									{ label: 'Agents and gateways', slug: 'concepts/agents' },
									{ label: 'The agent home', slug: 'concepts/agent-home' },
									{
										label: 'Conversations and records',
										slug: 'concepts/conversations',
									},
									{ label: 'Skills', slug: 'concepts/skills' },
								],
							},
						],
					},
					{
						label: 'Guides',
						link: '/guides/discord/',
						items: [
							{
								label: 'Everyday work',
								items: [
									{ label: 'Put an agent on Discord', slug: 'guides/discord' },
									{ label: 'Schedule work', slug: 'guides/schedules' },
									{ label: 'Back up and restore', slug: 'guides/backups' },
								],
							},
						],
					},
					{
						label: 'Reference',
						link: '/reference/providers/',
						items: [
							{
								label: 'The surface',
								items: [
									{ label: 'Providers', slug: 'reference/providers' },
									{ label: 'CLI reference', slug: 'reference/cli' },
								],
							},
						],
					},
					{
						label: 'Extend',
						link: '/extend/provider-adapters/',
						items: [
							{
								label: 'Write your own',
								items: [
									{ label: 'Provider adapters', slug: 'extend/provider-adapters' },
									{ label: 'Channel adapters', slug: 'extend/channel-adapters' },
									{ label: 'Integration CLIs', slug: 'extend/integration-clis' },
								],
							},
						],
					},
				], {
					// The overview belongs to no area — it is the page you land on
					// before choosing one, so it gets no left panel at all.
					exclude: ['/'],
				}),
			],
		}),
		// After Starlight, which is what its manual-MDX setup requires.
		mdx(),
	],
});
