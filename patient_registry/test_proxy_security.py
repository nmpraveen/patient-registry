from ipaddress import ip_network

from django.core.exceptions import ImproperlyConfigured, SuspiciousOperation
from django.test import RequestFactory, SimpleTestCase, override_settings

from patient_registry.proxy_security import (
    TrustedProxyClientIPMiddleware,
    normalized_ip,
    parse_proxy_cidrs,
    trusted_client_ip,
)


TRUSTED_CADDY = (ip_network("172.30.0.10/32"),)


class TrustedProxyClientIPTests(SimpleTestCase):
    def test_spoofed_header_from_untrusted_peer_is_ignored(self):
        meta = {"REMOTE_ADDR": "203.0.113.9", "HTTP_X_MEDTRACK_CLIENT_IP": "198.51.100.4"}
        self.assertEqual(trusted_client_ip(meta, TRUSTED_CADDY), "203.0.113.9")

    def test_untrusted_direct_peer_uses_remote_addr(self):
        self.assertEqual(trusted_client_ip({"REMOTE_ADDR": "198.51.100.8"}, TRUSTED_CADDY), "198.51.100.8")

    def test_trusted_caddy_overwrites_remote_addr_and_removes_header(self):
        request = RequestFactory().get(
            "/login/", REMOTE_ADDR="172.30.0.10", HTTP_X_MEDTRACK_CLIENT_IP="203.0.113.11"
        )
        middleware = TrustedProxyClientIPMiddleware(lambda current: current.META["REMOTE_ADDR"])
        with override_settings(MEDTRACK_TRUSTED_PROXY_NETWORKS=TRUSTED_CADDY):
            self.assertEqual(middleware(request), "203.0.113.11")
        self.assertNotIn("HTTP_X_MEDTRACK_CLIENT_IP", request.META)

    def test_trusted_proxy_rejects_spoofed_chain_or_missing_header(self):
        with self.assertRaises(SuspiciousOperation):
            trusted_client_ip(
                {"REMOTE_ADDR": "172.30.0.10", "HTTP_X_MEDTRACK_CLIENT_IP": "1.1.1.1, 2.2.2.2"},
                TRUSTED_CADDY,
            )
        with self.assertRaises(SuspiciousOperation):
            trusted_client_ip({"REMOTE_ADDR": "172.30.0.10"}, TRUSTED_CADDY)

    def test_ipv4_and_ipv6_are_canonicalized(self):
        self.assertEqual(normalized_ip(" 192.0.2.1 "), "192.0.2.1")
        self.assertEqual(normalized_ip("2001:0db8:0:0:0:0:0:1"), "2001:db8::1")

    def test_multiple_clients_resolve_to_distinct_backend_bucket_inputs(self):
        first = trusted_client_ip(
            {"REMOTE_ADDR": "172.30.0.10", "HTTP_X_MEDTRACK_CLIENT_IP": "203.0.113.1"}, TRUSTED_CADDY
        )
        second = trusted_client_ip(
            {"REMOTE_ADDR": "172.30.0.10", "HTTP_X_MEDTRACK_CLIENT_IP": "203.0.113.2"}, TRUSTED_CADDY
        )
        self.assertNotEqual(first, second)

    def test_proxy_allowlist_requires_canonical_network_notation(self):
        with self.assertRaises(ImproperlyConfigured):
            parse_proxy_cidrs("172.30.0.10/24")
        self.assertEqual(parse_proxy_cidrs("172.30.0.10/32"), TRUSTED_CADDY)
