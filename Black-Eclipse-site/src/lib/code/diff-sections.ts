// Split a unified diff into per-file sections for review. Pure, tolerant of
// quoted paths and of a diff that has no `diff --git` header.

export interface DiffSection {
  path: string;
  text: string;
}

const GIT_HEADER = /^diff --git a\/(.+?) b\/(.+)$/;
const PLUS_HEADER = /^\+\+\+ b\/(.+)$/;

export function splitUnifiedDiff(unified: string): DiffSection[] {
  if (!unified || !unified.trim()) return [];
  const sections: Array<{ path: string; lines: string[] }> = [];
  let current: { path: string; lines: string[] } | null = null;

  for (const line of unified.split(/\r?\n/)) {
    const header = line.match(GIT_HEADER);
    if (header) {
      current = { path: clean(header[2]), lines: [line] };
      sections.push(current);
      continue;
    }
    if (!current) {
      current = { path: 'change', lines: [] };
      sections.push(current);
    }
    if (current.path === 'change') {
      const plus = line.match(PLUS_HEADER);
      if (plus) current.path = clean(plus[1]);
    }
    current.lines.push(line);
  }

  return sections.map((section) => ({
    path: section.path,
    text: section.lines.join('\n'),
  }));
}

function clean(path: string): string {
  let value = path.trim();
  if (value.startsWith('"') && value.endsWith('"')) value = value.slice(1, -1);
  return value.replace(/^b\//, '');
}
