"""Explicit RFC1918 LAN ranges, independent of Python's broader is_private flag."""
from ipaddress import IPv4Address, IPv4Network

LAN_RANGES = tuple(IPv4Network(cidr) for cidr in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))


def is_lan_address(address: IPv4Address) -> bool:
    return any(address in network for network in LAN_RANGES)


def is_lan_network(network: IPv4Network) -> bool:
    return any(network.subnet_of(private) for private in LAN_RANGES)
