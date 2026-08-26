from __future__ import annotations

from .model import DiscrepancyCategory, PositionSnapshot, ReconciliationResult


def reconcile_positions(
    expected: PositionSnapshot | None,
    actual: list[PositionSnapshot],
    *,
    quantity_tolerance: float = 1e-9,
    price_tolerance: float = 1e-9,
) -> ReconciliationResult:
    actual_by_symbol = {position.symbol.upper(): position for position in actual}
    discrepancies: list[DiscrepancyCategory] = []
    actual_position = actual_by_symbol.get(expected.symbol.upper()) if expected else (actual[0] if actual else None)
    if expected is not None and actual_position is None:
        discrepancies.append(DiscrepancyCategory.MISSING_POSITION)
    if expected is not None and actual_position is not None:
        if expected.side != actual_position.side:
            discrepancies.append(DiscrepancyCategory.POSITION_SIDE_MISMATCH)
        if abs(expected.quantity - actual_position.quantity) > quantity_tolerance:
            discrepancies.append(DiscrepancyCategory.POSITION_QUANTITY_MISMATCH)
        if expected.average_price is not None and actual_position.average_price is not None:
            if abs(expected.average_price - actual_position.average_price) > price_tolerance:
                discrepancies.append(DiscrepancyCategory.AVERAGE_PRICE_MISMATCH)
    expected_symbols = {expected.symbol.upper()} if expected else set()
    if expected is None:
        unexpected = actual_by_symbol
    else:
        unexpected = {symbol: position for symbol, position in actual_by_symbol.items() if symbol not in expected_symbols}
    discrepancies.extend(DiscrepancyCategory.UNEXPECTED_POSITION for _ in sorted(unexpected))
    return ReconciliationResult(
        "MATCH" if not discrepancies else "DISCREPANCY",
        tuple(discrepancies),
        expected,
        actual_position,
    )
