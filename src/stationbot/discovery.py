"""Bounded home-network port discovery. A candidate is never treated as a qualified model."""
import asyncio
import ipaddress

from .errors import InvalidInput
from .network import is_lan_network


async def discover(cidr: str) -> list[str]:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        if network.version != 4 or network.prefixlen < 24 or not is_lan_network(network):
            raise ValueError
    except ValueError as e:
        raise InvalidInput("Укажите LAN IPv4-подсеть /24 или меньше из 10.x, 172.16–31.x или 192.168.x; VPN fake-IP 198.18.x не подходит. Например /discover 192.168.1.0/24") from e
    slots = asyncio.Semaphore(64)

    async def probe(host) -> str | None:
        async with slots:
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection(str(host), 5555), .35)
                writer.close()
                await writer.wait_closed()
                return str(host)
            except (OSError, asyncio.TimeoutError):
                return None
    return [value for value in await asyncio.gather(*(probe(ip) for ip in network.hosts())) if value]
