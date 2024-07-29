import random
import math

class Sampling:

    def __init__(self, data):
        self.data = data

    def __calculate_sample_size(self, confidence_level: float, margin_of_error: float, population_size: int) -> int:
        Z = 1.96  # Z-score for 95% confidence
        p = 0.5   # Proportion (maximum variability)
        E = margin_of_error

        n_0 = (Z**2 * p * (1 - p)) / E**2
        n = n_0 / (1 + ((n_0 - 1) / population_size))
        
        return math.ceil(n)

    def sample(self) -> tuple[int, int, int, int]:
        # Calculate sample size
        N = len(self.data)
        confidence_level = 0.95
        margin_of_error = 0.05
        sample_size = self.__calculate_sample_size(confidence_level, margin_of_error, N)

        # Systematic sampling
        k = N // sample_size

        start = random.randint(0, k-1)

        return N, sample_size, k, start