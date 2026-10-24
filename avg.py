class AverageCalculator:
    """Calculate the average of a collection of numbers."""

    def __init__(self, numbers):
        self.numbers = numbers

    def calculate_average(self):
        """Return the average value."""
        if not self.numbers:
            raise ValueError("The list cannot be empty.")

        return sum(self.numbers) / len(self.numbers)

    def calculate_average2(self):
        """Return the average value using the shared calculation."""
        return self.calculate_average()


def display_average(numbers):
    """Create an object and display the average."""
    average_calculator = AverageCalculator(numbers)
    average = average_calculator.calculate_average()
    print(f"Numbers: {numbers}")
    print(f"Average: {average:.2f}")


# Example usage
sample_numbers = [10, 20, 30, 40, 50]
display_average(sample_numbers)