"""Agent Client Protocol (ACP) adapter — a wire surface over the runtime."""

from .server import PROTOCOL_VERSION, AcpError, AcpServer, main

__all__ = ["PROTOCOL_VERSION", "AcpError", "AcpServer", "main"]
