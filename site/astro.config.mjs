// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
	site: 'https://docs.rundesk.ai',
	integrations: [
		starlight({
			title: 'Rundesk',
			description:
				'Run AI coding agents as durable, named teammates on your own Mac — then reach them from your terminal, Discord, or a schedule.',
			tagline: 'Teammates that remember, adapt, and grow.',
			logo: {
				src: './src/assets/rundesk-mark.png',
				alt: 'Rundesk',
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
			sidebar: [
				{
					label: 'Start here',
					items: [
						{ label: 'What Rundesk is', slug: 'start/what-rundesk-is' },
						{ label: 'Install', slug: 'start/install' },
						{ label: 'Your first agent', slug: 'start/first-agent' },
					],
				},
				{
					label: 'Concepts',
					items: [
						{ label: 'Agents and gateways', slug: 'concepts/agents' },
						{ label: 'The agent home', slug: 'concepts/agent-home' },
						{ label: 'Conversations and records', slug: 'concepts/conversations' },
						{ label: 'Skills', slug: 'concepts/skills' },
					],
				},
				{
					label: 'Guides',
					items: [
						{ label: 'Put an agent on Discord', slug: 'guides/discord' },
						{ label: 'Schedule work', slug: 'guides/schedules' },
						{ label: 'Back up and restore', slug: 'guides/backups' },
					],
				},
				{
					label: 'Reference',
					items: [
						{ label: 'Providers', slug: 'reference/providers' },
						{ label: 'CLI reference', slug: 'reference/cli' },
					],
				},
				{
					label: 'Extend',
					items: [
						{ label: 'Provider adapters', slug: 'extend/provider-adapters' },
						{ label: 'Channel adapters', slug: 'extend/channel-adapters' },
						{ label: 'Integration CLIs', slug: 'extend/integration-clis' },
					],
				},
			],
		}),
	],
});
