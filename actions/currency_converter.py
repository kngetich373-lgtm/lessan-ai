# actions/currency_converter.py
# Lessan AI — Sample Action Module
#
# Demonstrates the standard action-module pattern:
#   1. One entry-point function with the canonical signature
#   2. Reads args from `parameters`
#   3. Never raises — returns a friendly result string
#   4. Uses `player.write_log(...)` for UI logging when player is provided
#
# NOTE: This file lives in the flat actions/ package. Import as
# `from actions.currency_converter import currency_converter`.

_RATES_USD = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "TRY": 34.2,
    "JPY": 149.5,
    "INR": 83.9,
}


def currency_converter(
    parameters:     dict,
    response:       None = None,
    player:         None = None,
    session_memory: None = None,
) -> str:
    """
    Convert an amount from one currency to another.

    parameters:
        amount        : Amount to convert (required)
        from_currency : Source ISO code, e.g. USD (default: USD)
        to_currency   : Target ISO code, e.g. EUR (default: EUR)
    """
    params = parameters or {}

    try:
        amount = float(params.get("amount", 0))
    except (TypeError, ValueError):
        return "Please provide a valid amount to convert, sir."

    from_currency = (params.get("from_currency") or "USD").strip().upper()
    to_currency   = (params.get("to_currency")   or "EUR").strip().upper()

    if amount <= 0:
        return "The amount must be greater than zero, sir."

    if from_currency not in _RATES_USD:
        return (
            f"Sorry sir, I don't have a rate for {from_currency}. "
            f"Supported: {', '.join(sorted(_RATES_USD))}."
        )
    if to_currency not in _RATES_USD:
        return (
            f"Sorry sir, I don't have a rate for {to_currency}. "
            f"Supported: {', '.join(sorted(_RATES_USD))}."
        )

    usd       = amount / _RATES_USD[from_currency]
    converted = round(usd * _RATES_USD[to_currency], 2)

    result = (
        f"{amount:,.2f} {from_currency} = {converted:,.2f} {to_currency} "
        f"(approximate reference rate)."
    )

    print(f"[CurrencyConverter] 💱 {amount} {from_currency} → {converted} {to_currency}")
    if player:
        player.write_log(f"[currency] {result}")

    return result