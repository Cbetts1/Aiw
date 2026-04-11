"""
AIM Transport Layer — TLS helpers and transport utilities.

    from aim.transport import create_client_ssl_context, create_server_ssl_context

All public deployments MUST terminate TLS.  Plain TCP is acceptable only
for localhost development.
"""

from aim.transport.tls import (
    create_client_ssl_context,
    create_server_ssl_context,
    open_aim_connection,
    start_aim_server,
)

__all__ = [
    "create_client_ssl_context",
    "create_server_ssl_context",
    "open_aim_connection",
    "start_aim_server",
]
