from sqlalchemy import UniqueConstraint

from app.modules.steven.models import StevenQuoteOfferLine


def test_offer_line_has_supplier_item_composite_unique_constraint() -> None:
    constraints = [constraint for constraint in StevenQuoteOfferLine.__table__.constraints if isinstance(constraint, UniqueConstraint)]
    assert any(
        tuple(column.name for column in constraint.columns) == ("quote_supplier_id", "quote_item_id")
        and constraint.name == "uq_steven_quote_offer_lines_supplier_item"
        for constraint in constraints
    )