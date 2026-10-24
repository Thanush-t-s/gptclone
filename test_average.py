import pytest

from avg import AverageCalculator, display_average


def test_calculate_average_returns_average_for_integers():
    calculator = AverageCalculator([10, 20, 30, 40, 50])

    assert calculator.calculate_average() == 30


def test_calculate_average_returns_average_for_decimal_values():
    calculator = AverageCalculator([1.5, 2.5, 3.5])

    assert calculator.calculate_average() == 2.5


def test_calculate_average_raises_error_for_empty_list():
    calculator = AverageCalculator([])

    with pytest.raises(ValueError, match="The list cannot be empty."):
        calculator.calculate_average()


def test_calculate_average2_matches_calculate_average():
    calculator = AverageCalculator([4, 8, 12])

    assert calculator.calculate_average2() == calculator.calculate_average()


def test_display_average_prints_numbers_and_average(capsys):
    display_average([10, 20, 30])

    captured_output = capsys.readouterr().out

    assert "Numbers: [10, 20, 30]" in captured_output
    assert "Average: 20.00" in captured_output
