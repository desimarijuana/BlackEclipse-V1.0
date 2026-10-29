"""Broker connectivity for Eclipse.

P0 is deliberately READ-ONLY: it connects, probes, and reads accounts,
positions, working orders and quotes. It has no order-submission path. A broker
connection is a runtime-owned row (never a secret bag), and every adapter must
report an honest unavailable reason instead of pretending a broker is reachable.

`trading.paper_order` in `graph_runtime/trading_nodes.py` remains the only
execution adapter. Live execution is a separate, gated phase.
"""

from .adapter import AdapterUnavailable, BrokerAdapter
from .model import BrokerConnection, BrokerKind, ConnectionMode
from .registry import list_kinds, make_adapter, register_kind
from .service import BrokerService

__all__ = [
    "AdapterUnavailable",
    "BrokerAdapter",
    "BrokerConnection",
    "BrokerKind",
    "BrokerService",
    "ConnectionMode",
    "list_kinds",
    "make_adapter",
    "register_kind",
]
