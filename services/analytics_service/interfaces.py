from abc import ABC, abstractmethod
from typing import List


class AnalyticsService(ABC):

    @abstractmethod
    def generate_heatmap(self, observations: List[dict]) -> dict:
        ...

    @abstractmethod
    def species_distribution(self, species_name: str) -> dict:
        ...

    @abstractmethod
    def density_estimation(self, bbox: tuple) -> dict:
        ...

# Future implementations:
# class PostGISAnalyticsService(AnalyticsService): ...
