"""
Agents package for IndusMind AI.

Implements the Hybrid RAG Pipeline and Multi-Agent Orchestrator:
- Retrieval: combines ChromaDB semantic search + Knowledge Graph + metadata
- LLM: Google Gemini integration with retries and token management
- Orchestrator: query understanding, strategy selection, response building
- Context: prompt construction with citations and token limits
- Memory: session-level conversation memory
"""
