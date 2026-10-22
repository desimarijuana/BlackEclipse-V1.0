# eclipse_data

Eclipse's data and research from a notebook. The runtime is the authority; this
package is a thin client for it, so a notebook and the app see the **same**
bars, the **same** verdict and the **same** project.

```bash
pip install -e Black-Eclipse-site/sdk/eclipse_data
```

```python
import eclipse_data as ed

bars = ed.get_bars("AAPL", interval="1d", start="2024-01-01", end="2024-06-30")
print(bars["provenance"])

for project in ed.list_projects():
    print(project["id"], project["name"])

report = ed.edge_report("exp_abc123")
print(report["verdict"]["grade"], report["verdict"]["summary"])

fit = ed.prop_firm(bars_of_my_strategy, firm="topstep", size="50k")
print(fit["monteCarlo"]["passProbability"])
```

## Where it points

The client talks to the **local Eclipse runtime** by default
(`http://127.0.0.1:8765`) and authenticates with the runtime's operator token
when one is configured (`CRON_SECRET`). Override with `ECLIPSE_HARNESS_URL` or
`EclipseData(base_url=..., token=...)`.

Start the runtime with `npm run dev` (it boots the Python runtime alongside the
app).

## What it will not do

- It never invents a value. A refusal from the runtime is raised as an
  `EclipseRuntimeError` with the runtime's own code and message.
- It never averages two data sources. The runtime's verification policy decides
  whether a series is verified, conflicted or failed.
- It needs no data vendor of its own: it reads what the runtime has, which
  includes the history the runtime has already cached locally.
