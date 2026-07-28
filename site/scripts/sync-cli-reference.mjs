/**
 * File `CLI.md` as the documentation site's CLI reference.
 *
 * `CLI.md` is generated from this repository's argument parser and the gate fails
 * when it and the command disagree, so copying it here rather than writing a
 * reference by hand keeps the published surface honest: a verb that lands in the
 * parser reaches the docs on the next build, and there is no third copy free to
 * drift from the other two.
 *
 * It reads the checkout it lives in. Nothing is fetched, so a build is offline and
 * documents the code beside it rather than whatever was published last.
 */
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const source = join(root, 'CLI.md');
const target = join(root, 'docs', 'reference', 'cli.md');

/** Strip the leading `# ...` — Starlight renders the title from frontmatter. */
function withoutTitle(body) {
	return body.replace(/^#\s+.*\n+/, '');
}

/**
 * `CLI.md` points at its neighbours the way a file in this repository would —
 * `.knowledge/guides/...`, `src/templates/...`. Those resolve against the repo and
 * not against a docs host, so left alone they publish as dead links.
 */
function withRepoLinks(body) {
	const blob = 'https://github.com/rundesk-ai/rundesk-cli/blob/main/';
	return body.replace(
		/\]\((?!https?:|#|\/)([^)]+)\)/g,
		(_, path) => `](${blob}${path.replace(/^\.\//, '')})`,
	);
}

let body;
try {
	body = await readFile(source, 'utf8');
} catch (reason) {
	console.error(
		`sync-cli-reference: could not read ${source} (${reason.code ?? reason}). ` +
			'Generate it from the parser, then build again.',
	);
	process.exit(1);
}

const page = `---
title: CLI reference
description: Every Rundesk command and argument, generated from the parser.
sidebar:
  order: 2
---

:::note
This page is generated from Rundesk's argument parser, so it cannot drift from the
installed command. Fix a wording problem in the parser, not here.
:::

${withRepoLinks(withoutTitle(body))}`;

await mkdir(dirname(target), { recursive: true });
await writeFile(target, page, 'utf8');
console.log('sync-cli-reference: wrote docs/reference/cli.md from CLI.md');
