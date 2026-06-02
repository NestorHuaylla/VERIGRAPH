PATTERNS = {
    "guaranteed_return": ["ganancia garantizada", "duplica tu dinero", "100% garantizado"],
    "urgency": ["solo hoy", "ultimos cupos", "urgente"],
    "advance_payment": ["pago adelantado", "adelanto", "deposito primero"],
    "crypto_payment": ["btc", "usdt", "wallet", "crypto"],
}


def extract_text_signals(text: str) -> list[dict]:
    lowered = text.lower()
    signals: list[dict] = []
    for code, terms in PATTERNS.items():
        matches = [term for term in terms if term in lowered]
        if matches:
            signals.append({"code": code, "matches": matches})
    return signals

