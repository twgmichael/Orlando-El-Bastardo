import logging
from typing import Optional
from agent.adapters.base import Adapter

log = logging.getLogger(__name__)


class AdapterRegistry:
    def __init__(self):
        self._adapters: list[Adapter] = []

    def register(self, adapter: Adapter) -> None:
        self._adapters.append(adapter)
        log.info("Registered adapter: %s", adapter.name)

    def find_adapter(self, job: dict) -> Optional[Adapter]:
        for adapter in self._adapters:
            if adapter.can_handle(job):
                return adapter
        return None
