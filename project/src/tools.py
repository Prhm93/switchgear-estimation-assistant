"""Tools for interacting with the product catalog (synthetic data)."""

PRICES = {
    "mccb": 145.00,
    "acb": 2850.00,
    "busbar": 95.00,
    "current transformer": 38.00,
    "cable gland": 25.00,
}


def lookup_price(part_name: str) -> str:
    """Return the unit price of one part, as text (for example 95.0).
    Valid part names: mccb (moulded case circuit breaker),
    acb (air circuit breaker), busbar (copper busbar, per metre),
    current transformer, cable gland.
    Use the exact name in lowercase.
    If the name is not valid, the reply says so and lists the valid part names.
    """
    #Normalize the part name before look up
    name = part_name.strip().lower()
    if name in PRICES:
        return str(PRICES[name])
    return f"unknown part '{part_name}'. Valid part: {', '.join(PRICES)}"


def list_parts() -> str:
    """List every part in the catalog, separated by commas."""
    return ", ".join(PRICES)

def line_total(unit_price: float, quantity: int) -> float:
    """Return the total price for one quote line, rounded to 2 decimal places.
    unit_price is the price of one item in pounds. Use the value from lookup_price.
    quantity is the number of items, as a whole number.
    """
    # Round to 2 decimals so the amount is a clean currency value
    return round(unit_price * quantity, 2)