// ── Journal PDF export — client-side report of the trade list ────────────────
// Heavy deps (jsPDF + autotable) are dynamically imported so they stay out of
// the main bundle, matching the response exporter's approach.

import type { TradeRecord } from "./types";

function money(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Build and download a PDF of the given trades (respects current filters). */
export async function tradesToPdf(trades: TradeRecord[]): Promise<void> {
  const { default: JsPDF } = await import("jspdf");
  const { autoTable } = await import("jspdf-autotable");

  const doc = new JsPDF({ unit: "pt", format: "a4", orientation: "landscape" });
  const margin = 32;

  const netPnl = trades.reduce((s, t) => s + t.pnl, 0);
  const netR = trades.reduce((s, t) => s + t.rMultiple, 0);
  const wins = trades.filter((t) => t.rMultiple > 0).length;
  const winRate = trades.length > 0 ? (wins / trades.length) * 100 : 0;

  doc.setFontSize(16);
  doc.setTextColor(20, 20, 20);
  doc.text("Trading Journal", margin, margin + 4);
  doc.setFontSize(10);
  doc.setTextColor(90, 90, 90);
  doc.text(
    `${trades.length} trades · win rate ${winRate.toFixed(1)}% · net ${money(netPnl)} · net R ${netR.toFixed(2)}`,
    margin,
    margin + 20,
  );
  doc.text(`Generated ${new Date().toISOString().slice(0, 10)}`, margin, margin + 34);

  autoTable(doc, {
    margin: { left: margin, right: margin },
    startY: margin + 48,
    head: [["Date", "Symbol", "Dir", "Entry", "Exit", "R", "P&L", "Session", "Setup", "Emotion", "Grade"]],
    body: trades.map((t) => [
      t.exitTime.slice(0, 10),
      t.symbol,
      t.direction,
      String(t.entry),
      String(t.exit),
      t.rMultiple.toFixed(2),
      money(t.pnl),
      t.session ?? "—",
      t.setupName ?? "—",
      t.emotion ?? "—",
      t.grade ?? "—",
    ]),
    styles: { fontSize: 8, cellPadding: 4, textColor: [30, 30, 30] },
    headStyles: { fillColor: [22, 22, 24], textColor: [230, 230, 230] },
    alternateRowStyles: { fillColor: [245, 245, 246] },
    theme: "grid",
  });

  const stamp = new Date().toISOString().slice(0, 10);
  doc.save(`trading-journal-${stamp}.pdf`);
}
