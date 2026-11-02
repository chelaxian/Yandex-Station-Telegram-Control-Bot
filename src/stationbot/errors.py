class BotError(Exception):
    """Safe, user-facing failure; never include tokens, URLs or request bodies."""


class Unavailable(BotError):
    pass


class TransportError(BotError):
    pass


class Forbidden(BotError):
    pass


class InvalidInput(BotError):
    pass
