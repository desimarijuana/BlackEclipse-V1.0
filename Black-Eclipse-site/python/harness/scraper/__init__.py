"""The scraper lane — collect data the vault does not have, on demand.

When the answer is not in JDdS, the agent can WRITE a scraper for the site that
has it and run it here. The lane is deliberately narrow:

  * the program runs in the SAME analysis sandbox (no raw sockets, no files
    outside its own folder, no other processes);
  * its only way out is the host-mediated `web_page` binding — the same
    SSRF-hardened transport, size cap and timeout the read-only tools use — so a
    generated scraper cannot become an SSRF or exfiltration primitive;
  * the first use of a DOMAIN needs the operator's approval; after that the
    domain is remembered, so the user approves a site once, not a scraper;
  * what comes back is COLLECTED page data: never a verified source, never
    silently promoted into a canonical market table.
"""

from __future__ import annotations

__all__ = ["__doc__"]
