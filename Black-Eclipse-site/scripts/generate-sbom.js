#!/usr/bin/env node
/**
 * Generate the public dependency inventory: a CycloneDX 1.5 SBOM and a
 * human-readable third-party notices file.
 *
 * Sources are the two locked trees, so the output is reproducible without a
 * network call:
 *   - package-lock.json (npm, lockfileVersion 3)
 *   - python/requirements.lock (uv pip compile --generate-hashes)
 *
 * Licences come from lockfile metadata. When a lockfile does not declare a
 * licence (most Python packages), the inventory says so instead of guessing.
 *
 * Usage (from Black-Eclipse-site/):
 *   npm run sbom
 *   node scripts/generate-sbom.js --check   # exit 1 if committed output is stale
 */
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const APP_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(APP_ROOT, '..');
const NOTICES_PATH = path.join(REPO_ROOT, 'THIRD-PARTY-NOTICES.md');
const SBOM_PATH = path.join(REPO_ROOT, 'sbom.cdx.json');
const CHECK = process.argv.includes('--check');

const NOASSERTION = 'NOASSERTION';

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function npmComponents() {
  const lock = readJson(path.join(APP_ROOT, 'package-lock.json'));
  if (!lock.packages) throw new Error('package-lock.json has no "packages" map');
  const out = [];
  for (const [key, meta] of Object.entries(lock.packages)) {
    if (!key || !meta.version) continue;
    const name = key.replace(/^.*node_modules\//, '');
    if (!name) continue;
    const purlName = name.startsWith('@') ? `%40${name.slice(1)}` : name;
    out.push({
      ecosystem: 'npm',
      type: 'library',
      name,
      version: meta.version,
      license: meta.license || NOASSERTION,
      scope: meta.dev ? 'optional' : 'required',
      purl: `pkg:npm/${purlName}@${encodeURIComponent(meta.version)}`,
      hashes: meta.integrity ? [{ alg: 'SHA-512', content: String(meta.integrity).replace(/^sha512-/, '') }] : [],
      resolved: meta.resolved || undefined,
    });
  }
  return out;
}

function pythonComponents() {
  const file = path.join(APP_ROOT, 'python', 'requirements.lock');
  const text = fs.readFileSync(file, 'utf8');
  const seen = new Set();
  const out = [];
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\]+)/);
    if (!m) continue;
    const name = m[1];
    const version = m[2];
    const id = `${name.toLowerCase()}==${version}`;
    if (seen.has(id)) continue;
    seen.add(id);
    out.push({
      ecosystem: 'pypi',
      type: 'library',
      name,
      version,
      license: NOASSERTION,
      scope: 'required',
      purl: `pkg:pypi/${name.toLowerCase().replace(/[_.]+/g, '-')}@${encodeURIComponent(version)}`,
      hashes: [],
    });
  }
  return out;
}

function licenseField(license) {
  if (license === NOASSERTION) return [{ license: { name: NOASSERTION } }];
  // A bare SPDX id uses license.id; anything with operators/parens is an
  // SPDX expression, which CycloneDX carries in its own field.
  if (/^[A-Za-z0-9.+-]+$/.test(license)) return [{ license: { id: license } }];
  return [{ expression: license }];
}

function componentJson(c) {
  const component = {
    type: c.type,
    'bom-ref': c.purl,
    name: c.name,
    version: c.version,
    purl: c.purl,
    scope: c.scope,
    licenses: licenseField(c.license),
  };
  if (c.hashes.length) component.hashes = c.hashes;
  if (c.resolved) component.externalReferences = [{ type: 'distribution', url: c.resolved }];
  return component;
}

function serialFor(components) {
  const digest = crypto.createHash('sha256').update(JSON.stringify(components)).digest('hex');
  const hex = digest.slice(0, 32).split('');
  hex[12] = '4'; // version 4
  hex[16] = '8'; // RFC 4122 variant
  const s = hex.join('');
  return `urn:uuid:${s.slice(0, 8)}-${s.slice(8, 12)}-${s.slice(12, 16)}-${s.slice(16, 20)}-${s.slice(20)}`;
}

function buildSbom(components) {
  const pkg = readJson(path.join(APP_ROOT, 'package.json'));
  return {
    bomFormat: 'CycloneDX',
    specVersion: '1.5',
    serialNumber: serialFor(components),
    version: 1,
    metadata: {
      timestamp: process.env.SOURCE_DATE_EPOCH
        ? new Date(Number(process.env.SOURCE_DATE_EPOCH) * 1000).toISOString()
        : new Date().toISOString(),
      tools: [{ vendor: 'BlackEclipse', name: 'generate-sbom.js' }],
      component: {
        type: 'application',
        'bom-ref': `pkg:npm/black-eclipse@${pkg.version}`,
        name: 'black-eclipse',
        version: pkg.version,
        licenses: [{ license: { id: pkg.license || 'MIT' } }],
      },
    },
    components: components.map(componentJson),
  };
}

function buildNotices(components) {
  const byLicense = new Map();
  for (const c of components) {
    const key = c.license;
    if (!byLicense.has(key)) byLicense.set(key, []);
    byLicense.get(key).push(c);
  }
  const licenses = [...byLicense.keys()].sort((a, b) => {
    if (a === NOASSERTION) return 1;
    if (b === NOASSERTION) return -1;
    return a.localeCompare(b);
  });
  const pkg = readJson(path.join(APP_ROOT, 'package.json'));
  const npm = components.filter((c) => c.ecosystem === 'npm');
  const py = components.filter((c) => c.ecosystem === 'pypi');
  const lines = [];
  lines.push('# Third-Party Notices');
  lines.push('');
  lines.push('Generated by `npm run sbom` (`scripts/generate-sbom.js`) from the');
  lines.push(`locked trees. Do not hand-edit; regenerate after a lockfile change.`);
  lines.push('');
  lines.push(`- Application: \`black-eclipse\` ${pkg.version} - MIT (see \`LICENSE\`).`);
  lines.push(`- Components: **${components.length}** (${npm.length} npm, ${py.length} Python).`);
  lines.push('- The Pine Script engine in `Black-Eclipse-site/pine-engine/` is a');
  lines.push('  separate program under **AGPL-3.0-only** (see its `NOTICE.md`).');
  lines.push('');
  lines.push('> Licence values are read from `package-lock.json`. Python packages do not');
  lines.push('> declare a licence in `python/requirements.lock`, so they are listed as');
  lines.push(`> \`${NOASSERTION}\`: check the installed package metadata before redistributing a`);
  lines.push('> bundled runtime. A missing licence here is not a claim that none applies.');
  lines.push('');
  lines.push('## Summary by licence');
  lines.push('');
  lines.push('| Licence | Components |');
  lines.push('| --- | ---: |');
  for (const license of licenses) {
    lines.push(`| ${license} | ${byLicense.get(license).length} |`);
  }
  lines.push('');
  for (const license of licenses) {
    const items = byLicense.get(license).slice().sort((a, b) => a.name.localeCompare(b.name));
    lines.push(`## ${license}`);
    lines.push('');
    for (const c of items) {
      lines.push(`- \`${c.name}@${c.version}\` (${c.ecosystem}${c.scope === 'optional' ? ', dev' : ''})`);
    }
    lines.push('');
  }
  return lines.join('\n');
}

function dedupe(components) {
  // npm hoists the same package@version to several node_modules paths. An SBOM
  // identifies a component by purl, so collapse duplicates and keep the
  // strongest scope (a package used by production is not "dev").
  const map = new Map();
  for (const c of components) {
    const prev = map.get(c.purl);
    if (!prev) {
      map.set(c.purl, { ...c });
      continue;
    }
    if (c.scope === 'required') prev.scope = 'required';
    if (!prev.hashes.length && c.hashes.length) prev.hashes = c.hashes;
    if (!prev.resolved && c.resolved) prev.resolved = c.resolved;
  }
  return [...map.values()];
}

function main() {
  const components = dedupe([...npmComponents(), ...pythonComponents()])
    .sort((a, b) => (a.purl < b.purl ? -1 : a.purl > b.purl ? 1 : 0));
  const sbom = `${JSON.stringify(buildSbom(components), null, 2)}\n`;
  const notices = buildNotices(components);

  if (CHECK) {
    const stale = [];
    for (const [file, next] of [[SBOM_PATH, sbom], [NOTICES_PATH, notices]]) {
      const prev = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
      // The timestamp changes every run; compare everything else.
      const strip = (s) => s.replace(/"timestamp": "[^"]+"/, '"timestamp": ""');
      if (strip(prev) !== strip(next)) stale.push(path.relative(REPO_ROOT, file));
    }
    if (stale.length) {
      console.error(`[sbom] stale: ${stale.join(', ')}. Run npm run sbom.`);
      process.exit(1);
    }
    console.log('[sbom] up to date');
    return;
  }

  fs.writeFileSync(SBOM_PATH, sbom);
  fs.writeFileSync(NOTICES_PATH, notices);
  console.log(`[sbom] ${components.length} components -> ${path.relative(REPO_ROOT, SBOM_PATH)}, ${path.relative(REPO_ROOT, NOTICES_PATH)}`);
}

main();
