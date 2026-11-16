# 2. Argentina policy rate

- runId: `run_57f8eed9-88ce-4879-86f6-4324355d134d`
- status: **completed**
- steps: 24 / tools: 46 / toolErrors: 1
- provider: ollama / model: deepseek-v4.1-flash:cloud
- createdAt: 2026-11-16T18:09:42.044Z / finishedAt: 2026-11-16T18:15:30.817Z

## Prompt

What is the current policy rate in Argentina? If FRED has no series, use the central bank page and cite it.

## Answer

## Short answer

I could **not** confirm a published headline "tasa de polÃ­tica monetaria" from the BCRA in this run, and **FRED carries no Argentina policy-rate series at all**. What the central bank's own statistical service does publish, as of **12 November 2026**, is a money-market complex clustered in the low-20s, with the **1-day interbank repo (pases entre terceros a 1 dÃ­a) at 22.48% nominal annual** â the closest observable operational anchor.

## What FRED has

FRED's own search for "argentina policy rate" returns 123 series, but **none of them is an Argentine policy rate** â the hits are the BIS real/nominal effective exchange rates, OECD CPI and trade series, exchange rates, IMF projections and the *Kansas City Fed's US* policy-rate uncertainty measures. My direct attempts at the standard OECD/FRED codes for an Argentine short-term policy rate (`IRSTCI01ARM156N`, `IRSTCB01ARM156N`) came back **not registered / HTTP 404** on both the macro tool and the fredgraph CSV endpoint. So: FRED = no series, as you anticipated. (source: fred.stlouisfed.org search results page, retrieved 2026-11-16)

## What the BCRA actually publishes

Direct from the BCRA's official statistics API (v4.0, `Principales Variables` and the monetary series catalogue), latest observations:

| BCRA series (official name) | Value | Basis | As of |
|---|---|---|---|
| Pases entre terceros a 1 dÃ­a (1-day interbank repo rate) | **22.48%** | Nominal annual, ARS | 2026-11-12 |
| BAIBAR (private interbank lending) | 22.39% | Nominal annual, ARS | 2026-11-12 |
| TM20 (private banks, 20-day avg) | 22.63% | Nominal annual, ARS | 2026-11-12 |
| BADLAR (private banks) | 22.13% (24.50% effective) | Nominal / effective annual | 2026-11-12 |
| TAMAR (private banks) | 24.31% (27.20% effective) | Nominal / effective annual | 2026-11-12 |
| 30-day time deposit rate | 21.22% | Nominal annual, ARS | 2026-11-12 |
| LELIQ / NOTALQ stock | ARS 0 mn | Balance | 2026-11-12 |
| BCRA pases pasivos / activos stock | ARS 0 mn | Balance | 2026-11-12 |

Sources: `https://api.bcra.gob.ar/estadisticas/v4.0/monetarias?limit=14&offset=0` (Principales Variables), `.../monetarias?limit=100&offset=100` (rates and monetary-regulation series, ids 135â158) and `.../monetarias/7?limit=3&offset=0` (BADLAR observations). The BCRA's public "Principales variables" page (`bcra.gob.ar/PublicacionesEstadisticas/Principales_variables.asp`) lists the same panel of rates but carries **no line labelled "tasa de polÃ­tica monetaria"**.

## The limit you should know about

The BCRA has reorganised its operational framework repeatedly (LELIQ â pases â repos), and its statistics catalogue names instruments rather than a single "policy rate". The **zero balances** on LELIQ/NOTALQ and on BCRA pases as of 12 Nov 2026 confirm those legacy instruments are not the active anchor â which points to a repo-based framework where the 1-day repo around **22.5% n.a.** is the operative reference. But that inference is mine from the instrument stocks, not a BCRA statement I retrieved. The BCRA's policy pages (`/PoliticaMonetaria/`, `/Noticias.asp`) returned HTTP 404 in this run, and `scraper_run` was refused (write-effect not approved for this session), so I could not pull the confirming press release or the ComunicaciÃ³n that fixes the rate.

To close the gap precisely, the one thing needed is the BCRA's **ComunicaciÃ³n de polÃ­tica monetaria / tasa de pases** announcement page (bcra.gob.ar â PolÃ­tica Monetaria â Comunicados) â either approving site access for the scraper or an MCP/web route that renders that page would settle whether the headline rate is 22.5% or set at a different facility. Until then: **22.48% n.a. (1-day repo, 12-Nov-2026) is the best central-bank-sourced number, and it is an instrument rate, not a confirmed "policy rate" label.**

Advisory note: the following recommendation(s) are not backed by a portfolio calculation or a consulted source, so they are unverified advice, not verified analysis: short OECD FRED.

More I can do: I can run with write access for "What is the current policy rate in Argentina? If FRED has no series, use the central bank page and cite it." (Tool error (TOOL_FORBIDDEN): Tool 'scraper_run' has effect 'write' and is not approved for this call [recovery] This call failed. Failure kind: authorization (non_retryable). Next step: stop and report â this needs a decision outside the run. Do NOT repeat the same call with the same arguments. Reason: a credential or permission is required; request authorized consent (incident inc_09634e1c-bd4b-4). Want me to?

More I can do: I can set it up for "What is the current policy rate in Argentina? If FRED has no series, use the central bank page and cite it." (analysis isn't turned on for this session). Want me to?
