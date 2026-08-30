"""Trusted reverse-proxy client address handling for authentication controls."""

from __future__ import annotations

from ipaddress import ip_address, ip_network

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousOperation


CLIENT_IP_META_HEADER = "HTTP_X_MEDTRACK_CLIENT_IP"


def parse_proxy_cidrs(value: str):
    networks = []
    for item in value.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        try:
            network = ip_network(candidate, strict=False)
        except ValueError as exc:
            raise ImproperlyConfigured(f"Invalid MEDTRACK_TRUSTED_PROXY_CIDRS entry: {candidate}") from exc
        if str(network) != candidate:
            raise ImproperlyConfigured(
                f"MEDTRACK_TRUSTED_PROXY_CIDRS must use canonical exact/CIDR notation: {candidate}"
            )
        networks.append(network)
    return tuple(networks)


def normalized_ip(value: str) -> str:
    try:
        return ip_address((value or "").strip()).compressed.lower()
    except ValueError as exc:
        raise SuspiciousOperation("Invalid network peer address") from exc


def trusted_client_ip(meta, trusted_networks=None) -> str:
    remote = ip_address(normalized_ip(meta.get("REMOTE_ADDR", "")))
    networks = settings.MEDTRACK_TRUSTED_PROXY_NETWORKS if trusted_networks is None else trusted_networks
    if not any(remote in network for network in networks):
        return remote.compressed.lower()

    forwarded = meta.get(CLIENT_IP_META_HEADER, "")
    if not forwarded or "," in forwarded:
        raise SuspiciousOperation("Trusted proxy supplied a missing or ambiguous client address")
    return normalized_ip(forwarded)


class TrustedProxyClientIPMiddleware:
    """Replace REMOTE_ADDR only for the exact reviewed Caddy network identity."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.META["REMOTE_ADDR"] = trusted_client_ip(request.META)
        request.META.pop(CLIENT_IP_META_HEADER, None)
        return self.get_response(request)
