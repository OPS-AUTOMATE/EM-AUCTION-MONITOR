from enum import Enum, IntEnum

class FetchTier(IntEnum):
    NORMAL = 0   # > 8h
    CLOSING = 1  # < 8h
    URGENT = 2   # < 1h
    CRITICAL = 3 # < 10m

# Interval mapping in SECONDS only
TIER_INTERVALS_SECONDS = {
    FetchTier.NORMAL: 10800,   # 3 hours
    FetchTier.CLOSING: 3600,   # 1 hour
    FetchTier.URGENT: 120,     # 2 minutes
    FetchTier.CRITICAL: 30,    # 30 seconds
}

class Status(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    EXPIRED = "expired"
    ERROR = "error"

class FetchMethod(IntEnum):
    HTTP = 0
    HTML = 1
    PLAYWRIGHT = 2
