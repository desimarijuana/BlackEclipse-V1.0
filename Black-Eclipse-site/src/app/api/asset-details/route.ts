import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { MARKET_CURRENCY } from "@/lib/market-currency";
import { commodityDef, forexDef } from "@/lib/market-catalog";
import { resolveIndex } from "@/lib/indices";
import { fetchYahooChartSeries, yahooChartCandidates } from "@/lib/scraper/yahoo-chart";

export const dynamic = "force-dynamic";

// Helpers shared with /api/stocks for consistent formatting.
function formatVol(v: number): string {
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(v);
}

function formatCap(v: number): string {
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  return String(v);
}

function supplyFmt(v?: number | null): string {
  if (v == null) return "N/A";
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return `${Math.floor(v)}`;
}

// GET /api/asset-details?symbol=OGDC&market=PK
//
// Full detail record for the stock-detail overlay. Resolves ANY asset type in
// JDDS (stocks, ETFs, funds, crypto, warrants, foreign listings) and returns
// every field we track so the detail page is never limited to what the
// screener row happened to carry. Cross-market duplicates resolve by
// preferring priced rows, then US.
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = (searchParams.get("symbol") || "").trim().toUpperCase();
  const marketHint = (searchParams.get("market") || "").trim().toUpperCase() || null;

  if (!symbol) {
    return NextResponse.json({ found: false, error: "symbol required" }, { status: 400 });
  }

  try {
    const rows = await prisma.asset.findMany({
      where: {
        symbol,
        isActive: true,
        ...(marketHint ? { marketId: marketHint } : {}),
      },
      include: { price: true },
      take: 10,
    });

    if (rows.length === 0) {
      // Commodities and FX are served by their own feeds, not JDDS. Resolve
      // their identity here so the detail overlay shows a proper name/exchange
      // instead of "not found" (the live price comes from /api/commodities or
      // /api/forex and is merged by the caller).
      const comm = commodityDef(symbol);
      const fx = forexDef(symbol);
      if (comm || fx) {
        const isFx = Boolean(fx);
        return NextResponse.json({
          found: true,
          asset: {
            symbol,
            name: comm?.name ?? fx!.name,
            sector: isFx ? 'Foreign Exchange' : 'Commodity',
            industry: comm?.unit ?? 'Currency pair',
            country: 'GLOBAL',
            securityType: isFx ? 'Currency Pair' : 'Commodity Future',
            assetClass: isFx ? 'FX' : 'Commodity',
            marketId: isFx ? 'FX' : 'COMMODITY',
            currency: 'USD',
            price: 0, changePercent: 0, volume: 'N/A', volumeRaw: 0,
            marketCap: 'N/A', marketCapRaw: 0, peRatio: 'N/A', forwardPE: 'N/A',
            dividendYield: 'N/A', dividendRate: 'N/A', eps: 'N/A', beta: 'N/A',
            dayHigh: null, dayLow: null, dayOpen: null, previousClose: null,
            fiftyTwoWeekHigh: null, fiftyTwoWeekLow: null,
            circulatingSupply: 'N/A', totalSupply: 'N/A', maxSupply: 'N/A',
            ath: 'N/A', atl: 'N/A', athChangePercent: 0, atlChangePercent: 0, fdv: 'N/A',
            source: isFx ? 'forex' : 'commodity',
            updatedAt: new Date().toISOString(),
          },
        });
      }

      // Indices live in IndexQuote (keyed by canonical ticker + aliases).
      const def = resolveIndex(symbol);
      const indexSymbols = def
        ? [def.symbol.toUpperCase(), ...def.aliases.map((a) => a.toUpperCase()), symbol]
        : [symbol];
      const idx = await prisma.indexQuote.findFirst({ where: { symbol: { in: indexSymbols } } });
      if (idx && idx.price > 0) {
        const marketId = idx.marketId || 'US';
        return NextResponse.json({
          found: true,
          asset: {
            symbol: idx.symbol, name: idx.name, sector: 'Index', industry: 'Index',
            country: marketId, securityType: 'Index', assetClass: 'Index', marketId,
            currency: MARKET_CURRENCY[marketId] || '$',
            price: idx.price, changePercent: idx.changePct ?? 0, volume: 'N/A', volumeRaw: 0,
            marketCap: 'N/A', marketCapRaw: 0, peRatio: 'N/A', forwardPE: 'N/A',
            dividendYield: 'N/A', dividendRate: 'N/A', eps: 'N/A', beta: 'N/A',
            dayHigh: null, dayLow: null, dayOpen: null, previousClose: null,
            fiftyTwoWeekHigh: null, fiftyTwoWeekLow: null,
            circulatingSupply: 'N/A', totalSupply: 'N/A', maxSupply: 'N/A',
            ath: 'N/A', atl: 'N/A', athChangePercent: 0, atlChangePercent: 0, fdv: 'N/A',
            source: 'index', updatedAt: idx.updatedAt ? new Date(idx.updatedAt).toISOString() : null,
          },
        });
      }

      // On-demand resolution: a symbol the vault has never ingested (SPY, SGOV,
      // any Yahoo-resolvable instrument). Resolve it live so "all assets" open,
      // instead of a dead "not found".
      for (const cand of yahooChartCandidates(symbol, marketHint || 'US')) {
        const chart = await fetchYahooChartSeries(cand, '1mo', '1d');
        if (chart) {
          const meta = chart.meta;
          const marketId = marketHint || 'US';
          return NextResponse.json({
            found: true,
            asset: {
              symbol,
              name: meta.longName || meta.shortName || symbol,
              sector: 'Other', industry: 'Other',
              country: marketId, securityType: meta.instrumentType || 'Unknown', assetClass: 'Other',
              marketId,
              currency: meta.currency || MARKET_CURRENCY[marketId] || '$',
              price: meta.price ?? 0,
              changePercent: meta.changePct ?? 0,
              volume: 'N/A', volumeRaw: 0, marketCap: 'N/A', marketCapRaw: 0,
              peRatio: 'N/A', forwardPE: 'N/A', dividendYield: 'N/A', dividendRate: 'N/A',
              eps: 'N/A', beta: 'N/A',
              dayHigh: null, dayLow: null, dayOpen: null, previousClose: meta.previousClose ?? null,
              fiftyTwoWeekHigh: null, fiftyTwoWeekLow: null,
              circulatingSupply: 'N/A', totalSupply: 'N/A', maxSupply: 'N/A',
              ath: 'N/A', atl: 'N/A', athChangePercent: 0, atlChangePercent: 0, fdv: 'N/A',
              source: 'yahoo', updatedAt: new Date().toISOString(),
            },
          });
        }
      }

      return NextResponse.json({ found: false });
    }

    // Deterministic winner: prefer priced rows, then the hint market, then US.
    const rank = (r: (typeof rows)[number]) =>
      (r.price && r.price.price > 0 ? 4 : 0) +
      (marketHint && r.marketId === marketHint ? 2 : 0) +
      (r.marketId === "US" ? 1 : 0);
    let best = rows[0];
    for (const r of rows) {
      if (rank(r) > rank(best)) best = r;
    }

    const p = best.price;
    const marketId = best.marketId;
    const isCrypto = marketId === "CRYPTO";

    return NextResponse.json({
      found: true,
      asset: {
        symbol: best.symbol,
        name: best.name,
        sector: best.sector || "Other",
        industry: best.industry || "Other",
        country: best.country || (isCrypto ? "CRYPTO" : marketId),
        securityType: best.securityType || (isCrypto ? "Crypto" : "Stock"),
        assetClass: best.assetClass || (isCrypto ? "Crypto" : "Equity"),
        marketId,
        currency: MARKET_CURRENCY[marketId] || "$",
        price: p?.price ?? 0,
        changePercent: p?.changePct ?? 0,
        volume: p?.volume != null && p.volume > 0 ? formatVol(p.volume) : "N/A",
        volumeRaw: p?.volume ?? 0,
        marketCap: p?.marketCap != null && p.marketCap > 0 ? formatCap(p.marketCap) : "N/A",
        marketCapRaw: p?.marketCap ?? 0,
        peRatio: p?.peRatio != null ? p.peRatio.toFixed(2) : "N/A",
        forwardPE: p?.forwardPE != null ? p.forwardPE.toFixed(2) : "N/A",
        dividendYield: p?.dividendYield != null && p.dividendYield > 0 ? `${p.dividendYield.toFixed(2)}%` : "None",
        dividendRate: p?.dividendRate != null ? p.dividendRate.toFixed(2) : "N/A",
        eps: p?.eps != null ? p.eps.toFixed(2) : "N/A",
        beta: p?.beta != null ? p.beta.toFixed(2) : "N/A",
        dayHigh: p?.dayHigh ?? null,
        dayLow: p?.dayLow ?? null,
        dayOpen: p?.open ?? null,
        previousClose: p?.previousClose ?? null,
        fiftyTwoWeekHigh: p?.fiftyTwoWeekHigh ?? null,
        fiftyTwoWeekLow: p?.fiftyTwoWeekLow ?? null,
        rank: p?.rank ?? undefined,
        circulatingSupply: supplyFmt(p?.circulatingSupply),
        circulatingSupplyRaw: p?.circulatingSupply ?? undefined,
        totalSupply: supplyFmt(p?.totalSupply),
        maxSupply: supplyFmt(p?.maxSupply),
        maxSupplyRaw: p?.maxSupply ?? undefined,
        ath: p?.ath != null ? String(p.ath) : "N/A",
        atl: p?.atl != null ? String(p.atl) : "N/A",
        athChangePercent: p?.athChangePct ?? 0,
        atlChangePercent: p?.atlChangePct ?? 0,
        fdv: p?.fdv != null ? formatCap(p.fdv) : "N/A",
        source: p?.source || null,
        updatedAt: p?.updatedAt ? new Date(p.updatedAt).toISOString() : null,
      },
    });
  } catch (err) {
    console.error("[api/asset-details] Error:", err);
    return NextResponse.json({ found: false, error: "lookup failed" }, { status: 500 });
  }
}