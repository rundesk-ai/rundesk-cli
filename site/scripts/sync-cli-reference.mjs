/**
 * Render the CLI reference page from `CLI.json`.
 *
 * `CLI.json` is walked off this repository's argument parser by
 * `.knowledge/scripts/cli-reference`, and the gate fails when it and the command
 * disagree — so the published reference documents the code beside it and there is
 * no third copy free to drift. A wording problem on this page is a parser problem.
 *
 * The aligned listing in `CLI.md` is the right shape for a terminal and the wrong
 * shape for a page: forty operations in one fence, signatures out to 273 columns,
 * and no anchor for any of them. Here each verb gets a heading of its own, its
 * operations, and the arguments it actually takes.
 *
 * It reads the checkout it lives in. Nothing is fetched, so a build is offline.
 */
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const source = join(root, 'CLI.json');
const target = join(root, 'docs', 'reference', 'cli.md');

/** A table cell is pipe-delimited, so a pipe inside one ends it early. */
function cell(text) {
	return String(text ?? '')
		.replace(/\|/g, '\\|')
		.trim();
}

function argumentTable(args) {
	if (!args.length) return [];
	return [
		'| Argument | Means |',
		'|---|---|',
		...args.map(({ written, means }) => `| \`${cell(written)}\` | ${cell(means)} |`),
		'',
	];
}

function verbSection(verb) {
	const out = [`### rundesk ${verb.verb}${verb.planned ? ' — planned' : ''}`, ''];
	if (verb.summary) out.push(verb.summary, '');

	// One fence per verb rather than one for the whole surface, so the copy button
	// copies this verb alone. `wrap` is what stops a 212-column signature — argparse
	// writes them, and `schedules add` is genuinely that long — becoming a
	// horizontal scrollbar the reader has to find.
	out.push('```sh wrap');
	for (const { signature, does } of verb.operations) {
		if (does) out.push(`# ${does}`);
		out.push(signature);
	}
	out.push('```', '');

	out.push(...argumentTable(verb.arguments));
	return out;
}

let surface;
try {
	surface = JSON.parse(await readFile(source, 'utf8'));
} catch (reason) {
	console.error(
		`sync-cli-reference: could not read ${source} (${reason.code ?? reason}). ` +
			'Generate it with `python3 .knowledge/scripts/cli-reference`, then build again.',
	);
	process.exit(1);
}

const body = [];
for (const group of surface.groups) {
	body.push(`## ${group.title}`, '');
	if (group.why) body.push(group.why, '');
	for (const verb of group.verbs) body.push(...verbSection(verb));
}

body.push(
	'## Every argument',
	'',
	'Gathered across the whole surface — the same few appear under verb after verb.',
	'',
	...argumentTable(surface.arguments),
	'## What it exits with',
	'',
	'| Code | Means |',
	'|---|---|',
	...surface.exits.map(({ code, means }) => `| \`${code}\` | ${cell(means)} |`),
	'',
);

const page = `---
title: CLI reference
description: Every Rundesk command and argument, generated from the parser.
sidebar:
  order: 3
tableOfContents:
  maxHeadingLevel: 3
---

A verb says **what**. The next word says **whose** — \`start ava\`, \`logs ava\`,
\`channels ava\`. A verb marked *planned* is registered and not built: it exits \`69\`
and changes nothing.

:::note
This page is generated from Rundesk's argument parser, so it cannot drift from the
installed command. Fix a wording problem in the parser, not here.
:::

${body.join('\n')}`;

await mkdir(dirname(target), { recursive: true });
await writeFile(target, page.replace(/\n{3,}/g, '\n\n'), 'utf8');
console.log(
	'sync-cli-reference: wrote docs/reference/cli.md — ' +
		`${surface.groups.reduce((n, g) => n + g.verbs.length, 0)} verbs from CLI.json`,
);
