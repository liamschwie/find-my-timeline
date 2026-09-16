"""Decode the AirTag battery-status byte into a human-readable level."""

_BATTERY_LEVELS = {0b00: "Full", 0b01: "Medium", 0b10: "Low", 0b11: "Very Low"}


def decode_battery(status: int) -> str:
    """Extract the battery level from a LocationReport status byte.

    The top two bits of the status byte encode battery level; the rest
    carry unrelated accessory flags.
    """
    battery_id = (status >> 6) & 0b11
    return _BATTERY_LEVELS.get(battery_id, "Unknown")
