"""
AIM Transport — TLS context helpers and connection factories.

These utilities wrap the standard-library ``ssl`` module to provide
TLS 1.2+ encrypted transport for AIM nodes.  No external dependencies are
required.

Public API
----------
create_client_ssl_context(verify, ca_file, cert_file, key_file)
    Build an ``ssl.SSLContext`` for outbound (client) TLS connections.

create_server_ssl_context(cert_file, key_file, ca_file, require_client_cert)
    Build an ``ssl.SSLContext`` for inbound (server) TLS connections.

open_aim_connection(host, port, ssl_context)
    Async helper: open a TLS (or plain TCP) connection to an AIM node.

start_aim_server(handler, host, port, ssl_context)
    Async helper: start a TLS (or plain TCP) AIM server.
"""

from __future__ import annotations

import asyncio
import ssl
from typing import Callable, Awaitable


# ---------------------------------------------------------------------------
# SSL context factories
# ---------------------------------------------------------------------------

def create_client_ssl_context(
    verify: bool = True,
    ca_file: str | None = None,
    cert_file: str | None = None,
    key_file: str | None = None,
) -> ssl.SSLContext:
    """
    Create an SSL context for outbound (client) AIM connections.

    Parameters
    ----------
    verify:
        Whether to verify the server's certificate.  Set to ``False`` only
        in development / testing with self-signed certificates.
    ca_file:
        Path to a CA bundle file in PEM format.  If ``None`` the default
        system CA store is used.
    cert_file:
        Path to the client certificate file (for mutual TLS).
    key_file:
        Path to the private key file matching *cert_file*.

    Returns
    -------
    ssl.SSLContext
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    if verify:
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        if ca_file:
            ctx.load_verify_locations(cafile=ca_file)
        else:
            ctx.load_default_certs()
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    if cert_file and key_file:
        ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)

    return ctx


def create_server_ssl_context(
    cert_file: str,
    key_file: str,
    ca_file: str | None = None,
    require_client_cert: bool = False,
) -> ssl.SSLContext:
    """
    Create an SSL context for inbound (server) AIM connections.

    Parameters
    ----------
    cert_file:
        Path to the server certificate file in PEM format.
    key_file:
        Path to the server private key file.
    ca_file:
        Path to a CA bundle for verifying client certificates (mutual TLS).
        Required when *require_client_cert* is ``True``.
    require_client_cert:
        If ``True``, enforce mutual TLS — clients must present a valid
        certificate signed by *ca_file*.

    Returns
    -------
    ssl.SSLContext
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)

    if require_client_cert:
        ctx.verify_mode = ssl.CERT_REQUIRED
        if ca_file:
            ctx.load_verify_locations(cafile=ca_file)
    else:
        ctx.verify_mode = ssl.CERT_NONE

    return ctx


# ---------------------------------------------------------------------------
# Async connection helpers
# ---------------------------------------------------------------------------

async def open_aim_connection(
    host: str,
    port: int,
    ssl_context: ssl.SSLContext | None = None,
    timeout: float = 10.0,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """
    Open a TCP or TLS connection to an AIM node.

    Parameters
    ----------
    host:
        Target hostname or IP address.
    port:
        Target TCP port.
    ssl_context:
        An ``ssl.SSLContext`` for TLS.  Pass ``None`` for plain TCP (localhost
        development only).
    timeout:
        Connection timeout in seconds.

    Returns
    -------
    (asyncio.StreamReader, asyncio.StreamWriter)

    Raises
    ------
    ConnectionRefusedError
        If the target node is not listening.
    asyncio.TimeoutError
        If the connection cannot be established within *timeout* seconds.
    """
    return await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=ssl_context),
        timeout=timeout,
    )


async def start_aim_server(
    handler: Callable[
        [asyncio.StreamReader, asyncio.StreamWriter],
        Awaitable[None],
    ],
    host: str = "0.0.0.0",
    port: int = 7700,
    ssl_context: ssl.SSLContext | None = None,
) -> asyncio.AbstractServer:
    """
    Start a TCP or TLS AIM server.

    Parameters
    ----------
    handler:
        Async callback invoked for each new connection.
    host:
        Interface to bind on.
    port:
        TCP port to listen on.
    ssl_context:
        An ``ssl.SSLContext`` for TLS.  Pass ``None`` for plain TCP.

    Returns
    -------
    asyncio.AbstractServer
        The running server object.  Call ``server.close()`` to stop it.
    """
    return await asyncio.start_server(handler, host, port, ssl=ssl_context)
