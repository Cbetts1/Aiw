"""
Meshara Transport Layer — TLS helpers and transport utilities.

    from meshara.transport import create_client_ssl_context, create_server_ssl_context

All public deployments MUST terminate TLS.  Plain TCP is acceptable only
for localhost development.
"""

from meshara.transport.tls import (
    create_client_ssl_context,
    create_server_ssl_context,
    open_meshara_connection,
    start_meshara_server,
)

__all__ = [
    "create_client_ssl_context",
    "create_server_ssl_context",
    "open_meshara_connection",
    "start_meshara_server",
]
