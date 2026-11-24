"""Casos sintéticos para demostrar la normalización y la conciliación local."""

import unittest
from decimal import Decimal

from procesar_presupuestos import (
    is_item_code,
    monetary_tolerance,
    normalize_description_key,
    normalize_item_code,
    normalize_ocr_number,
    normalize_unit,
    parse_ocr_number,
    recover_lost_decimal,
    within_tolerance,
)


class NumericParsingTests(unittest.TestCase):
    def test_decimal_with_comma(self):
        self.assertEqual(normalize_ocr_number("1.234,50"), Decimal("1234.50"))

    def test_decimal_with_point(self):
        self.assertEqual(normalize_ocr_number("1,234.50"), Decimal("1234.50"))

    def test_integer(self):
        self.assertEqual(normalize_ocr_number("84"), Decimal("84"))

    def test_currency_prefix(self):
        self.assertEqual(normalize_ocr_number("S/ 16,20"), Decimal("16.20"))

    def test_ambiguous_separator_requires_review(self):
        self.assertIsNone(parse_ocr_number("1,234").value)

    def test_two_tokens_are_not_silently_merged(self):
        self.assertIsNone(parse_ocr_number("12 34").value)

    def test_non_numeric_ocr_is_rejected(self):
        self.assertIsNone(parse_ocr_number("12O.00").value)

    def test_high_precision_requires_explicit_opt_in(self):
        self.assertIsNone(parse_ocr_number("2,3456").value)
        self.assertEqual(
            parse_ocr_number("2,3456", allow_high_precision=True).value,
            Decimal("2.3456"),
        )


class ReviewAndReconciliationTests(unittest.TestCase):
    def test_code_confusion_requires_evidence(self):
        uncertain = normalize_item_code("701.4")
        self.assertEqual(uncertain.normalized, "701.4")
        self.assertTrue(uncertain.review_reason)
        approved = normalize_item_code("701.4", evidence_codes={"701.A"})
        self.assertEqual(approved.normalized, "701.A")

    def test_code_with_decimal_levels(self):
        self.assertTrue(is_item_code("701.01"))

    def test_unrecognized_unit_is_marked_for_review(self):
        result = normalize_unit("xyz")
        self.assertEqual(result.normalized, "")
        self.assertTrue(result.review_reason)

    def test_description_key_ignores_accents(self):
        self.assertEqual(
            normalize_description_key("Área de ejemplo"),
            normalize_description_key("AREA DE EJEMPLO"),
        )

    def test_monetary_tolerance_has_absolute_floor(self):
        self.assertEqual(
            monetary_tolerance(Decimal("100"), Decimal("0.01")),
            Decimal("0.10"),
        )

    def test_reconciliation_accepts_small_rounding_difference(self):
        self.assertTrue(
            within_tolerance(Decimal("150.08"), Decimal("150.00"), Decimal("0.01"))
        )

    def test_reconciliation_rejects_larger_difference(self):
        self.assertFalse(
            within_tolerance(Decimal("150.20"), Decimal("150.00"), Decimal("0.01"))
        )

    def test_missing_decimal_recovered_only_with_math(self):
        result = recover_lost_decimal(
            "125", Decimal("8.00"), Decimal("100.00"), [1, 2]
        )
        self.assertEqual(result.value, Decimal("12.5"))
        self.assertTrue(result.rule)

    def test_missing_decimal_without_evidence_remains_reviewable(self):
        result = recover_lost_decimal("125", None, None, [])
        self.assertEqual(result.value, Decimal("125"))
        self.assertTrue(result.review_reason)


if __name__ == "__main__":
    unittest.main()
