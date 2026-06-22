"use client";

import React, { useState } from "react";
import { TopLoader } from "@/components/ui/top-loader";
import { 
  FileText, Calendar, LineChart, PlusCircle, Network, 
  Activity, AlertTriangle, PlayCircle, Clipboard
} from "lucide-react";

export default function ReportsPage() {
  const [reportType, setReportType] = useState<string>("daily_system");
  const [generating, setGenerating] = useState<boolean>(false);
  const [report, setReport] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch("/api/reports/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: reportType })
      });
      if (!res.ok) {
        throw new Error(`Server responded with HTTP ${res.status}`);
      }
      const data = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }
      setReport(data.report);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate report");
      setReport(null);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <>
      {generating && <TopLoader />}
      <div className="flex flex-col gap-8">
        {/* Header */}
        <div className="flex flex-col gap-1 border-b border-border/40 pb-5">
          <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-primary">Dynamic Reporting Engine</span>
          <h1 className="font-serif text-3xl font-semibold tracking-tight">System & Market Reports</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Compile executive summaries, API latency audits, and asset performance metrics directly from the live PostgreSQL database.
        </p>
      </div>

      {/* Grid: Control vs Report Display */}
      <div className="grid gap-8 lg:grid-cols-3">
        {/* Left Side: Selectors */}
        <div className="flex flex-col border border-border/40 bg-card/25 rounded-3xl p-6 shadow-sm gap-5">
          <h2 className="font-serif text-md font-bold text-foreground">Select Report Profile</h2>

          <div className="flex flex-col gap-3 font-mono text-xs">
            {[
              { id: "daily_system", title: "Daily System Report", icon: FileText, desc: "JDdS daemon status, connection states & counters." },
              { id: "weekly_market", title: "Weekly Market Report", icon: Calendar, desc: "Price trends, movers & index changes." },
              { id: "asset_performance", title: "Asset Performance", icon: LineChart, desc: "Highlight gainers/losers per asset class." },
              { id: "new_listings", title: "New Listings Report", icon: PlusCircle, desc: "Recently discovered symbols on Binance/Finnhub." },
              { id: "api_performance", title: "API Performance Audits", icon: Network, desc: "Gateway latency logs & rate-limiting checks." }
            ].map((opt) => {
              const isSelected = reportType === opt.id;
              const Icon = opt.icon;
              return (
                <button
                  key={opt.id}
                  onClick={() => setReportType(opt.id)}
                  className={`flex items-start gap-3 rounded-xl p-3 border text-left cursor-pointer transition-all ${
                    isSelected 
                      ? "bg-primary/10 border-primary text-foreground shadow-sm shadow-primary/5" 
                      : "bg-white/[0.01] border-border/5 text-muted-foreground hover:border-border/25 hover:text-foreground"
                  }`}
                >
                  <Icon className="h-4 w-4 mt-0.5 text-primary" />
                  <div className="flex flex-col gap-1">
                    <span className="font-bold">{opt.title}</span>
                    <span className="text-[10px] text-muted-foreground leading-normal">{opt.desc}</span>
                  </div>
                </button>
              );
            })}
          </div>

          <button
            onClick={handleGenerate}
            disabled={generating}
            className="flex items-center justify-center gap-2 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs py-3 mt-2 transition-all cursor-pointer disabled:opacity-50"
          >
            {generating ? (
              <>
                <Activity className="h-4 w-4 animate-spin" /> Compiling Data...
              </>
            ) : (
              <>
                <PlayCircle className="h-4 w-4" /> Run Live Aggregator
              </>
            )}
          </button>
        </div>

        {/* Right Side: Report Sheet */}
        <div className="lg:col-span-2 flex flex-col border border-border/40 bg-card/10 rounded-3xl p-6 min-h-[450px] shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 h-[150px] w-[150px] bg-primary/5 rounded-full blur-3xl" />
          
          {error && (
            <div className="flex flex-col items-center justify-center gap-2 text-center my-auto">
              <AlertTriangle className="h-10 w-10 text-rose-400 animate-bounce" />
              <span className="font-mono text-xs text-rose-400 font-bold">Incomplete Ingestion Report</span>
              <p className="font-mono text-[10px] text-muted-foreground max-w-sm">{error}</p>
            </div>
          )}

          {!report && !error && (
            <div className="flex flex-col items-center justify-center gap-3 text-center my-auto text-muted-foreground">
              <Clipboard className="h-10 w-10 opacity-40 text-primary" />
              <span className="font-serif text-sm">No Report Compiled Yet</span>
              <p className="text-xs max-w-sm">
                Select a profile on the left and click "Run Live Aggregator" to query and summarize database records.
              </p>
            </div>
          )}

          {report && (
            <div className="flex flex-col gap-6 w-full animate-fade-in">
              <div className="border-b border-border/10 pb-4">
                <span className="font-mono text-[9px] text-muted-foreground uppercase">Generated: {new Date(report.timestamp).toLocaleString()}</span>
                <h2 className="font-serif text-xl font-bold text-foreground mt-1">{report.title}</h2>
                <p className="text-xs text-muted-foreground mt-1">{report.description}</p>
              </div>

              {/* Layout for Daily System */}
              {reportType === "daily_system" && report.metrics && (
                <div className="grid gap-4 sm:grid-cols-2">
                  {report.metrics.map((m: any) => (
                    <div key={m.label} className="flex flex-col gap-1 border border-border/5 bg-white/[0.01] rounded-2xl p-4 font-mono text-xs">
                      <span className="text-muted-foreground text-[10px] uppercase">{m.label}</span>
                      <span className="text-sm font-bold text-foreground mt-1">{m.value}</span>
                    </div>
                  ))}
                  <div className="col-span-2 border border-border/5 bg-white/[0.01] rounded-2xl p-4 text-xs leading-relaxed text-muted-foreground">
                    <span className="font-mono text-[10px] text-foreground font-bold block mb-1">AGGREGATOR FINDINGS:</span>
                    {report.details}
                  </div>
                </div>
              )}

              {/* Layout for Weekly Market */}
              {reportType === "weekly_market" && (
                <div className="flex flex-col gap-5">
                  <div className="grid gap-4 sm:grid-cols-2">
                    {/* Crypto Gainers */}
                    <div className="flex flex-col gap-2">
                      <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider border-b border-border/5 pb-1">Top Gainers (Binance Crypto)</span>
                      {report.cryptoGainers?.map((c: any) => (
                        <div key={c.symbol} className="flex justify-between font-mono text-xs py-1 border-b border-border/5">
                          <span>{c.symbol}</span>
                          <span className="text-emerald-400 font-bold">+{c.change.toFixed(2)}%</span>
                        </div>
                      ))}
                    </div>

                    {/* Stock Gainers */}
                    <div className="flex flex-col gap-2">
                      <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-wider border-b border-border/5 pb-1">Top Gainers (US Equities)</span>
                      {report.stockGainers?.map((s: any) => (
                        <div key={s.symbol} className="flex justify-between font-mono text-xs py-1 border-b border-border/5">
                          <span>{s.symbol}</span>
                          <span className="text-emerald-400 font-bold">+{s.change.toFixed(2)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground border-t border-border/5 pt-4 leading-relaxed italic">{report.summary}</p>
                </div>
              )}

              {/* Layout for Asset Performance */}
              {reportType === "asset_performance" && report.performanceData && (
                <div className="grid gap-6 sm:grid-cols-2">
                  {/* Crypto Outperformers vs Underperformers */}
                  <div className="flex flex-col gap-4 border border-border/5 bg-white/[0.01] rounded-2xl p-4">
                    <span className="font-mono text-[10px] text-primary uppercase font-bold tracking-wider">Cryptocurrency Performance</span>
                    <div className="flex flex-col gap-2">
                      <span className="font-mono text-[9px] text-muted-foreground">TOP LEADERS:</span>
                      {report.performanceData.crypto.outperformers.map((c: any) => (
                        <div key={c.symbol} className="flex justify-between font-mono text-[11px]">
                          <span>{c.symbol}</span>
                          <span className="text-emerald-400 font-bold">+{c.change.toFixed(2)}%</span>
                        </div>
                      ))}
                    </div>
                    <div className="flex flex-col gap-2 border-t border-border/5 pt-3">
                      <span className="font-mono text-[9px] text-rose-400">LAGGARDS:</span>
                      {report.performanceData.crypto.underperformers.map((c: any) => (
                        <div key={c.symbol} className="flex justify-between font-mono text-[11px]">
                          <span>{c.symbol}</span>
                          <span className="text-rose-400 font-bold">{c.change.toFixed(2)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Stock Outperformers vs Underperformers */}
                  <div className="flex flex-col gap-4 border border-border/5 bg-white/[0.01] rounded-2xl p-4">
                    <span className="font-mono text-[10px] text-primary uppercase font-bold tracking-wider">Stock Equity Performance</span>
                    <div className="flex flex-col gap-2">
                      <span className="font-mono text-[9px] text-muted-foreground">TOP LEADERS:</span>
                      {report.performanceData.stock.outperformers.map((s: any) => (
                        <div key={s.symbol} className="flex justify-between font-mono text-[11px]">
                          <span>{s.symbol}</span>
                          <span className="text-emerald-400 font-bold">+{s.change.toFixed(2)}%</span>
                        </div>
                      ))}
                    </div>
                    <div className="flex flex-col gap-2 border-t border-border/5 pt-3">
                      <span className="font-mono text-[9px] text-rose-400">LAGGARDS:</span>
                      {report.performanceData.stock.underperformers.map((s: any) => (
                        <div key={s.symbol} className="flex justify-between font-mono text-[11px]">
                          <span>{s.symbol}</span>
                          <span className="text-rose-400 font-bold">{s.change.toFixed(2)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Layout for New Listings */}
              {reportType === "new_listings" && report.listings && (
                <div className="flex flex-col gap-5 font-mono text-xs">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="flex flex-col gap-1 border border-border/5 bg-white/[0.01] rounded-2xl p-4">
                      <span className="text-muted-foreground text-[10px] uppercase">New Cryptos Registered</span>
                      <span className="text-lg font-bold text-foreground mt-1">{report.listings.cryptoCount} symbols</span>
                    </div>
                    <div className="flex flex-col gap-1 border border-border/5 bg-white/[0.01] rounded-2xl p-4">
                      <span className="text-muted-foreground text-[10px] uppercase">New Stocks Registered</span>
                      <span className="text-lg font-bold text-foreground mt-1">{report.listings.stockCount} symbols</span>
                    </div>
                  </div>
                  <div className="border border-border/5 bg-white/[0.01] rounded-2xl p-4">
                    <span className="text-foreground text-[10px] font-bold block mb-2">RECENT FINDINGS SUMMARY:</span>
                    <p className="text-muted-foreground leading-relaxed font-sans">{report.findings}</p>
                  </div>
                </div>
              )}

              {/* Layout for API Performance */}
              {reportType === "api_performance" && report.latencies && (
                <div className="flex flex-col gap-4 font-mono text-xs">
                  <div className="flex flex-col gap-2">
                    <span className="text-[10px] text-muted-foreground uppercase mb-1">LATENCY PROFILES</span>
                    {report.latencies.map((l: any) => (
                      <div key={l.service} className="flex items-center justify-between border-b border-border/5 py-2">
                        <span>{l.service}</span>
                        <div className="flex items-center gap-3">
                          <span className="font-bold text-foreground">{l.time}</span>
                          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-lg ${
                            l.status === "Excellent" || l.status === "Healthy" ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                          }`}>{l.status}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="border border-border/5 bg-white/[0.01] rounded-2xl p-4 text-xs font-sans text-muted-foreground leading-relaxed mt-2">
                    <span className="font-mono text-[10px] text-foreground font-bold block mb-1">API ARCHITECTURE NOTE:</span>
                    {report.details}
                  </div>
                </div>
              )}

            </div>
          )}
        </div>
      </div>
    </div>
    </>
  );
}
