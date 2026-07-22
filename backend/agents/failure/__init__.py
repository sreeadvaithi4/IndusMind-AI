"""
Failure Intelligence Agent — lessons learned, historical incidents,
recurring failures, and organizational knowledge.

Reuses RAGRetrievalService and KnowledgeGraphService (no duplication).
"""

import re
import time
from dataclasses import dataclass, field

from agents.config import RAGConfig
from agents.retrieval import RAGRetrievalService, RetrievalResult


FAILURE_KEYWORDS = re.compile(
    r"\b(?:fail\w*|incident|breakdown|trip|alarm|shutdown|leak\w*|"
    r"vibrat\w*|overheat\w*|corrosion|fatigue|crack\w*|rupture|"
    r"explosion|fire|spill|release|loss)\b", re.IGNORECASE
)


@dataclass
class FailureIntelligenceResult:
    """Output of the Failure Intelligence Agent."""
    historical_incidents: list[dict] = field(default_factory=list)
    recurring_failures: list[dict] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    preventive_knowledge: list[str] = field(default_factory=list)
    failure_frequency: dict = field(default_factory=dict)
    best_practices: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "historical_incidents": self.historical_incidents,
            "recurring_failures": self.recurring_failures,
            "lessons_learned": self.lessons_learned,
            "preventive_knowledge": self.preventive_knowledge,
            "failure_frequency": self.failure_frequency,
            "best_practices": self.best_practices,
            "confidence": self.confidence,
        }


class FailureIntelligenceAgent:
    """Analyzes historical failures and generates organizational learning."""

    @classmethod
    def analyze(
        cls, query: str, query_embedding: list[float] | None = None,
        config: RAGConfig | None = None,
    ) -> FailureIntelligenceResult:
        if config is None:
            config = RAGConfig.from_settings()
        if not query:
            return FailureIntelligenceResult()

        # Retrieve failure-related documents
        retrieval = RAGRetrievalService.retrieve(
            query=f"failure incident {query}",
            query_embedding=query_embedding,
            config=config,
        )

        # Extract historical incidents from retrieval
        incidents = cls._extract_incidents(retrieval)
        recurring = cls._detect_recurring(retrieval)
        lessons = cls._extract_lessons(retrieval)
        preventive = cls._generate_preventive_knowledge(retrieval)
        best_practices = cls._generate_best_practices(query)

        confidence = min(len(retrieval.hits) / config.top_k, 1.0) * 0.7

        return FailureIntelligenceResult(
            historical_incidents=incidents,
            recurring_failures=recurring,
            lessons_learned=lessons,
            preventive_knowledge=preventive,
            failure_frequency={"total_hits": len(retrieval.hits)},
            best_practices=best_practices,
            confidence=confidence,
        )

    @classmethod
    def _extract_incidents(cls, retrieval: RetrievalResult) -> list[dict]:
        incidents = []
        for hit in retrieval.hits[:5]:
            if FAILURE_KEYWORDS.search(hit.content or ""):
                incidents.append({
                    "source": hit.source,
                    "content": (hit.content or "")[:200],
                    "document_id": hit.document_id,
                    "score": hit.score,
                })
        return incidents

    @classmethod
    def _detect_recurring(cls, retrieval: RetrievalResult) -> list[dict]:
        patterns: dict[str, int] = {}
        for hit in retrieval.hits:
            for match in FAILURE_KEYWORDS.finditer(hit.content or ""):
                word = match.group(0).lower()
                patterns[word] = patterns.get(word, 0) + 1
        return [{"pattern": k, "occurrences": v} for k, v in sorted(patterns.items(), key=lambda x: -x[1])[:5] if v > 1]

    @classmethod
    def _extract_lessons(cls, retrieval: RetrievalResult) -> list[str]:
        lessons = []
        for hit in retrieval.hits[:3]:
            if hit.content:
                lessons.append(f"From {hit.source}: {hit.content[:150]}")
        return lessons

    @classmethod
    def _generate_preventive_knowledge(cls, retrieval: RetrievalResult) -> list[str]:
        knowledge = []
        for hit in retrieval.hits[:3]:
            if hit.content and any(kw in (hit.content or "").lower() for kw in ("prevent", "avoid", "mitigate", "recommend")):
                knowledge.append(hit.content[:150])
        return knowledge if knowledge else ["Review maintenance history for preventive insights"]

    @classmethod
    def _generate_best_practices(cls, query: str) -> list[str]:
        practices = [
            "Conduct regular condition monitoring",
            "Follow OEM maintenance schedules",
            "Document all interventions and findings",
            "Perform post-incident root cause analysis",
            "Share lessons learned across teams",
        ]
        return practices[:4]
