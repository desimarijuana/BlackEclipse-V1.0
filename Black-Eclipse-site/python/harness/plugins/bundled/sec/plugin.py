"""Reference plugin: SEC EDGAR filings (public data, no key required)."""

from harness.plugins.sdk import Plugin, research_provider, tool


class SecPlugin(Plugin):
    def _base(self, ctx):  # noqa: ANN001
        return (ctx.config.get("apiBase") or "https://data.sec.gov").rstrip("/")

    @tool(
        name="company_filings",
        description="Recent EDGAR filings for a CIK.",
        schema={
            "type": "object",
            "properties": {"cik": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["cik"],
        },
    )
    async def company_filings(self, args, ctx):  # noqa: ANN001
        cik = str(args["cik"]).zfill(10)
        response = await ctx.http.get(
            f"{self._base(ctx)}/submissions/CIK{cik}.json",
            headers={"User-Agent": "BlackEclipse research contact@example.com"},
        )
        data = response.json()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accession = recent.get("accessionNumber", [])
        limit = min(int(args.get("limit", 10)), 40)
        filings = [
            {"form": forms[i], "date": dates[i], "accession": accession[i]}
            for i in range(min(limit, len(forms)))
        ]
        return {"cik": cik, "company": data.get("name"), "filings": filings}

    @research_provider("sec-filings", kinds=["filing"])
    def sec_filings(self):
        return None


plugin = SecPlugin
