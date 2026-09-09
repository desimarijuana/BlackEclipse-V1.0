// ── CSV parsing utilities (shared, dependency-free) ──────────────────────────

/** Parse a CSV string into an array of header-keyed row objects. */
export function parseCsv(text: string): Record<string, string>[] {
  const lines = text.trim().split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) return [];
  const rawHeader = lines[0].split(",").map((h) => h.trim().toLowerCase().replace(/^"|"$/g, ""));
  // Dedupe duplicate headers (e.g. MT4 has two "Price" / two "Time" columns)
  // by suffixing with .1, .2, ... so both values are preserved.
  const seen = new Map<string, number>();
  const header = rawHeader.map((h) => {
    const count = seen.get(h) ?? 0;
    seen.set(h, count + 1);
    return count === 0 ? h : `${h}.${count}`;
  });
  const rows: Record<string, string>[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = parseCsvLine(lines[i]);
    const rec: Record<string, string> = {};
    header.forEach((h, idx) => { rec[h] = (cells[idx] ?? "").trim(); });
    rows.push(rec);
  }
  return rows;
}

/** Parse a single CSV line handling quoted fields. */
export function parseCsvLine(line: string): string[] {
  const cells: string[] = [];
  let cur = "";
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQ && line[i + 1] === '"') { cur += '"'; i++; }
      else inQ = !inQ;
    } else if (ch === "," && !inQ) {
      cells.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  cells.push(cur);
  return cells;
}

/** Build a CSV string from a header + rows. */
export function toCsv(header: string[], rows: string[][]): string {
  const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  return [header.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n");
}
