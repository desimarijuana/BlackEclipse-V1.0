// Regenerate the cross-language node manifest from the TS registry.
// Run: npm run graph:manifest
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildNodeManifest } from '../src/lib/graph-studio/manifest';

const target = join(process.cwd(), 'src', 'lib', 'graph-studio', 'registry.manifest.json');
writeFileSync(target, `${JSON.stringify(buildNodeManifest(), null, 2)}\n`, 'utf8');
console.log(`wrote ${target}`);
