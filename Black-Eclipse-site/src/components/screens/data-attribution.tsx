"use client";

// Attribution required by included data providers. Kept as one small strip so
// the obligation is visible where the data is shown, not only during setup.
export function DataAttribution({ extra }: { extra?: string[] }) {
  const items = [
    "FRED — Courtesy of FRED, Federal Reserve Bank of St. Louis",
    "World Bank — CC BY 4.0",
    "Eurostat / ECB",
    "SEC EDGAR",
    "GDELT",
    "USGS",
    "NASA FIRMS",
    ...(extra ?? []),
  ];
  return (
    <p className="text-[9px] leading-relaxed text-muted-foreground/60">
      Data sources: {items.join(" · ")}
    </p>
  );
}
