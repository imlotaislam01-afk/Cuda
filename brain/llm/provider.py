
from abc import ABC, abstractmethod

from typing import Any

class LLMProvider(ABC):

    @abstractmethod

    def analyze(

        self,

        market_state: dict[str, Any],

        context: dict[str, Any],

    ) -> dict[str, Any]:

        raise NotImplementedError

class SafeMockLLMProvider(LLMProvider):

    def analyze(

        self,

        market_state: dict[str, Any],

        context: dict[str, Any],

    ) -> dict[str, Any]:

        return {

            "advisory": True,

            "bias": "NEUTRAL",

            "confidence": 0.0,

            "reason": "Mock provider. No external LLM configured.",

        }

