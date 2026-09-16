import { NextResponse } from "next/server";
import { queryEdges, iso2ForCountryId } from "@/lib/investor-eye/graph-data";
import { buildGraph } from "@/lib/investor-eye/graph";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/graph
// The relationship graph (spec §41) as render-ready nodes + links, aggregated
// from stored `Relationship` edges by the pure builder. Relational, not a graph
// database (ADR-011).
//
// Query params:
//   ?kinds=country,company,commodity   filter node kinds
//   ?minWeight=0.5                     drop weak edges
//   ?maxNodes=150                      bound the rendered node count
//   ?focus=<kind:id>                   return only that node's neighbourhood
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const kinds = (searchParams.get("kinds") ?? "").split(",").map((k) => k.trim()).filter(Boolean);
  const minWeightRaw = Number(searchParams.get("minWeight") ?? "0");
  const minWeight = Number.isFinite(minWeightRaw) ? Math.max(0, minWeightRaw) : 0;
  const maxNodesRaw = Number(searchParams.get("maxNodes") ?? "150");
  const maxNodes = Number.isFinite(maxNodesRaw) ? Math.max(5, Math.min(maxNodesRaw, 500)) : 150;
  const focus = searchParams.get("focus");

  try {
    const edges = await queryEdges({ minWeight, limit: 2000 });
    const graph = buildGraph(edges, {
      maxNodes,
      minWeight,
      kinds,
      // Companies are a large uniform population; cap them so the geopolitical
      // structure (countries, commodities, sectors, markets) stays readable.
      maxPerKind: { company: 45, security: 25 },
      iso2ForCountryId,
      provenance: edges.length > 0 ? "LIVE" : "UNAVAILABLE",
    });

    if (focus) {
      // Rebuild bounded to the focus node's neighbourhood.
      const focused = buildGraph(
        edges.filter((e) =>
          `${e.fromKind}:${e.fromId}` === focus || `${e.toKind}:${e.toId}` === focus,
        ),
        { maxNodes: 80, minWeight, kinds, iso2ForCountryId, provenance: graph.provenance },
      );
      return NextResponse.json({ ...focused, focus });
    }

    if (graph.links.length === 0 && edges.length === 0) {
      return NextResponse.json({
        ...graph,
        note: "No relationships have been derived yet. They are built from ingested events.",
      });
    }
    return NextResponse.json(graph);
  } catch (err) {
    console.error("[api/investor-eye/graph] error:", err);
    return NextResponse.json({
      nodes: [], links: [], totals: { edges: 0, nodes: 0, truncated: false },
      generatedAt: new Date().toISOString(), provenance: "UNAVAILABLE",
    });
  }
}
