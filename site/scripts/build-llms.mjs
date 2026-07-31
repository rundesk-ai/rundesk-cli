/**
 * Write `llms.txt` and `llms-full.txt` from the pages in `docs/`.
 *
 * Rundesk's readers are frequently agents — the shipped `using-rundesk` skill is
 * written for one running inside it — so a machine-readable index of this site is
 * not a novelty here. Both are generated rather than kept by hand, because an index
 * written once is the document that goes stale first.
 *
 * Runs after `sync-cli-reference`, so the generated CLI reference is included.
 */
import { readFile, readdir, writeFile } from 'node:fs/promises';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const pages = join(root, 'docs');
const out = join(here, '..', 'public');

const SITE = 'https://docs.rundesk.ai';

/** Sidebar order, so the index reads the way the site does rather than alphabetically. */
const AREAS = [
	['start', 'Start here'],
	['concepts', 'Concepts'],
	['guides', 'Guides'],
	['reference', 'Reference'],
	['extend', 'Extend'],
];

async function* walk(where) {
	for (const entry of await readdir(where, { withFileTypes: true })) {
		const path = join(where, entry.name);
		if (entry.isDirectory()) yield* walk(path);
		else if (/\.mdx?$/.test(entry.name)) yield path;
	}
}

/**
 * Title and description off the frontmatter block.
 *
 * Hand-parsed rather than pulled in as a dependency: the only keys read are two
 * scalars, and a YAML parser for that is a package this site does not need.
 */
function front(text) {
	const block = /^---\n([\s\S]*?)\n---/.exec(text);
	if (!block) return {};
	const read = (key) => {
		const line = new RegExp(`^${key}:\\s*(.+)$`, 'm').exec(block[1]);
		if (!line) return '';
		return line[1].trim().replace(/^['"]|['"]$/g, '');
	};
	// `sidebar.order` is what puts a page where a reader meets it, rather than where
	// the alphabet does — "What Rundesk is" before "Install" before "Your first agent".
	const order = /^\s+order:\s*(\d+)\s*$/m.exec(block[1]);
	return {
		title: read('title'),
		description: read('description'),
		order: order ? Number(order[1]) : Number.MAX_SAFE_INTEGER,
		body: text.slice(block[0].length),
	};
}

/** `docs/start/install.md` is served at `/start/install/`; `docs/index.mdx` at `/`. */
function url(path) {
	const slug = relative(pages, path).replace(/\.mdx?$/, '');
	return slug === 'index' ? `${SITE}/` : `${SITE}/${slug}/`;
}

const found = [];
for await (const path of walk(pages)) {
	const { title, description, order, body } = front(await readFile(path, 'utf8'));
	if (title) found.push({ path, title, description, order, body, url: url(path) });
}

const area = (page) => relative(pages, page.path).split('/')[0];
const overview = found.find((page) => area(page) === 'index.mdx');

const index = [
	'# Rundesk',
	'',
	'> A provider-agnostic multi-agent gateway for your own machine. Rundesk runs the coding',
	'> CLI you already use — Codex, Claude Code, Grok, Google Antigravity — as a durable, named',
	'> teammate with its own home, memory, skills, schedules, and channels, reachable from the',
	'> terminal, from Discord, or on a schedule.',
	'',
	'Rundesk is standard-library Python, runs on macOS, and needs no hosted service. Its command',
	'reference is generated from the argument parser, so it cannot describe a version nobody has.',
	'',
];

for (const [prefix, label] of AREAS) {
	const inArea = found
		.filter((page) => area(page) === prefix)
		.sort((a, b) => a.order - b.order || a.url.localeCompare(b.url));
	if (!inArea.length) continue;
	index.push(`## ${label}`, '');
	for (const page of inArea) {
		index.push(`- [${page.title}](${page.url})${page.description ? `: ${page.description}` : ''}`);
	}
	index.push('');
}

index.push(
	'## Optional',
	'',
	`- [Full documentation](${SITE}/llms-full.txt): every page above, concatenated.`,
	'- [Source](https://github.com/rundesk-ai/rundesk-cli): the repository, its issues, and every release.',
	'',
);

await writeFile(join(out, 'llms.txt'), index.join('\n'), 'utf8');

const ordered = [
	...(overview ? [overview] : []),
	...AREAS.flatMap(([prefix]) =>
		found
			.filter((page) => area(page) === prefix)
			.sort((a, b) => a.order - b.order || a.url.localeCompare(b.url)),
	),
];

const full = ordered.map((page) => `# ${page.title}\n\nSource: ${page.url}\n${page.body.trim()}\n`);
await writeFile(join(out, 'llms-full.txt'), full.join('\n---\n\n'), 'utf8');

console.log(`build-llms: wrote llms.txt and llms-full.txt (${ordered.length} pages)`);
