# app/core/errors.py
"""Domain errors. No HTTP knowledge here — a later file maps them to status codes."""


class SurgeError(Exception):
    """Base class for all expected business-rule failures."""


class PoolNotFound(SurgeError):
    pass


class ReservationNotFound(SurgeError):
    pass


class PoolSoldOut(SurgeError):
    pass


class InvalidTransition(SurgeError):
    pass