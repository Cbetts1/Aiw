"""Tests for the Meshara Transport Layer (meshara/transport/tls.py)."""

import ssl
import pytest

from meshara.transport.tls import (
    create_client_ssl_context,
    create_server_ssl_context,
    open_meshara_connection,
    start_meshara_server,
)


# ---------------------------------------------------------------------------
# SSL context creation
# ---------------------------------------------------------------------------

class TestCreateClientSSLContext:
    def test_returns_ssl_context(self):
        ctx = create_client_ssl_context(verify=False)
        assert isinstance(ctx, ssl.SSLContext)

    def test_no_verify_disables_cert_check(self):
        ctx = create_client_ssl_context(verify=False)
        assert ctx.verify_mode == ssl.CERT_NONE
        assert ctx.check_hostname is False

    def test_verify_mode_enables_cert_required(self):
        ctx = create_client_ssl_context(verify=True)
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True

    def test_minimum_tls_version_is_1_2(self):
        ctx = create_client_ssl_context(verify=False)
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2

    def test_with_ca_file_nonexistent_raises(self):
        with pytest.raises((FileNotFoundError, ssl.SSLError)):
            create_client_ssl_context(verify=True, ca_file="/nonexistent/ca.pem")

    def test_with_cert_and_key_nonexistent_raises(self):
        with pytest.raises((FileNotFoundError, ssl.SSLError, OSError)):
            create_client_ssl_context(
                verify=False,
                cert_file="/nonexistent/cert.pem",
                key_file="/nonexistent/key.pem",
            )


class TestCreateServerSSLContext:
    def test_missing_cert_raises(self):
        with pytest.raises((FileNotFoundError, ssl.SSLError, OSError)):
            create_server_ssl_context(
                cert_file="/nonexistent/server.crt",
                key_file="/nonexistent/server.key",
            )

    def test_signature_accepts_ca_file_param(self, tmp_path):
        """Verify the function accepts ca_file kwarg without error (file need not exist yet)."""
        import inspect
        sig = inspect.signature(create_server_ssl_context)
        assert "ca_file" in sig.parameters
        assert "require_client_cert" in sig.parameters


# ---------------------------------------------------------------------------
# open_meshara_connection — connection refused path
# ---------------------------------------------------------------------------

class TestOpenAimConnection:
    @pytest.mark.asyncio
    async def test_connection_refused_raises(self):
        """Connecting to a port nothing listens on raises ConnectionRefusedError."""
        with pytest.raises((ConnectionRefusedError, OSError)):
            await open_meshara_connection("127.0.0.1", 19999, ssl_context=None, timeout=2.0)

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        """Connecting to a non-routable host raises TimeoutError."""
        import asyncio
        # 192.0.2.x is TEST-NET-1 — reserved, nothing routes there
        with pytest.raises((asyncio.TimeoutError, OSError, ConnectionRefusedError)):
            await open_meshara_connection("192.0.2.1", 7700, ssl_context=None, timeout=0.1)


# ---------------------------------------------------------------------------
# start_meshara_server — basic lifecycle
# ---------------------------------------------------------------------------

class TestStartAimServer:
    @pytest.mark.asyncio
    async def test_server_starts_and_stops(self):
        import asyncio

        async def noop(reader, writer):
            writer.close()

        server = await start_meshara_server(noop, host="127.0.0.1", port=0, ssl_context=None)
        try:
            assert server is not None
            addr = server.sockets[0].getsockname()
            assert addr[0] == "127.0.0.1"
            assert addr[1] > 0
        finally:
            server.close()
            await server.wait_closed()

    @pytest.mark.asyncio
    async def test_server_accepts_connections(self):
        import asyncio

        received: list[bytes] = []

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            received.append(b"connected")
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

        server = await start_meshara_server(handler, host="127.0.0.1", port=0)
        addr = server.sockets[0].getsockname()
        try:
            # Connect a plain TCP client
            reader, writer = await asyncio.open_connection(addr[0], addr[1])
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            await asyncio.sleep(0.05)  # give handler time to run
            assert len(received) == 1
        finally:
            server.close()
            await server.wait_closed()
