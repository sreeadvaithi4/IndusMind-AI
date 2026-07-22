"""
Exception hierarchy for the Agents module.
"""


class AgentError(Exception):
    """Base exception for all agent/orchestration failures."""


class RetrievalError(AgentError):
    """Raised when hybrid retrieval fails."""


class LLMError(AgentError):
    """Raised when the LLM service fails."""


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""


class LLMRateLimitError(LLMError):
    """Raised when LLM rate limits are hit."""


class ContextOverflowError(AgentError):
    """Raised when context exceeds token limits."""


class OrchestrationError(AgentError):
    """Raised when the orchestrator encounters an unrecoverable error."""
