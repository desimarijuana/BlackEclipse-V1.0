"""Reference plugin: Binance public market data."""

from harness.plugins.sdk import Plugin, data_provider, tool


class BinancePlugin(Plugin):
    def _base(self, ctx):  # noqa: ANN001
        return (ctx.config.get("apiBase") or "https://api.binance.com").rstrip("/")

    @tool(
        name="ticker",
        description="Latest price for a symbol.",
        schema={"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    )
    async def ticker(self, args, ctx):  # noqa: ANN001
        response = await ctx.http.get(f"{self._base(ctx)}/api/v3/ticker/price",
                                      params={"symbol": args["symbol"].upper()})
        data = response.json()
        return {"symbol": data.get("symbol"), "price": float(data.get("price", 0))}

    @tool(
        name="klines",
        description="Historical candlesticks (OHLCV) for a symbol.",
        schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "interval": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["symbol"],
        },
    )
    async def klines(self, args, ctx):  # noqa: ANN001
        response = await ctx.http.get(
            f"{self._base(ctx)}/api/v3/klines",
            params={"symbol": args["symbol"].upper(), "interval": args.get("interval", "1d"),
                    "limit": min(int(args.get("limit", 30)), 500)},
        )
        rows = response.json()
        return [{"openTime": r[0], "open": float(r[1]), "high": float(r[2]),
                 "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])} for r in rows]

    @data_provider("binance-spot", kinds=["price", "ohlcv"])
    def binance_spot(self):
        return None


plugin = BinancePlugin
