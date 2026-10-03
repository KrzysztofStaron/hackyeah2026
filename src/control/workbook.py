from __future__ import annotations

COLUMNS = tuple("ABCDEFGHIJKLMNOPQRST")
LAST_ROW = 1000


def value_at(column: str, row: int) -> int:
    index = COLUMNS.index(column)
    return (index * 31 + row * 17) % 89 + 1


def preview() -> dict[str, object]:
    row = [{"cell": f"{column}12", "value": value_at(column, 12)} for column in COLUMNS]
    return {
        "file": "numbers.xlsx",
        "columns": list(COLUMNS),
        "rows": LAST_ROW,
        "cell": "B12",
        "value": value_at("B", 12),
        "row": row,
    }
