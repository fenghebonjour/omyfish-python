from abc import ABC, abstractmethod
from typing import Iterator


class ObservationSource(ABC):
    """Interface for external observation data providers."""

    @abstractmethod
    def source_name(self) -> str:
        ...

    @abstractmethod
    def fetch_observations(self) -> Iterator[dict]:
        ...

# Future implementations:
# class INaturalistSource(ObservationSource): ...
# class GBIFSource(ObservationSource): ...
# class GovernmentDatasetSource(ObservationSource): ...
