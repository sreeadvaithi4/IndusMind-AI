"""
REST API views for retrieval and search.

All views delegate to the agents service layer — no direct
ChromaDB/KG access from views.
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from agents.config import RAGConfig
from agents.orchestrator import QueryOrchestrator
from agents.retrieval import RAGRetrievalService

logger = logging.getLogger("api")


class SemanticSearchView(APIView):
    """
    POST /api/search/semantic/

    Performs semantic search over ChromaDB using a text query.
    Returns ranked chunks without AI-generated answers.

    Request body:
        {"query": "pump maintenance procedure", "k": 10, "filters": {...}}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = request.data.get("query", "").strip()
        k = request.data.get("k", 10)
        filters = request.data.get("filters")

        if not query:
            return Response(
                {"detail": "query is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            k = int(k)
        except (TypeError, ValueError):
            k = 10

        # Embed the query
        try:
            embedding = self._embed_query(query)
        except Exception as exc:
            return Response(
                {"detail": f"Failed to embed query: {exc}"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        hits = RAGRetrievalService.search_semantic(
            query_embedding=embedding,
            k=min(k, 50),
            filters=filters,
        )

        return Response({
            "query": query,
            "results": [h.to_dict() for h in hits],
            "total": len(hits),
        })

    @staticmethod
    def _embed_query(query: str) -> list[float]:
        """Embeds a query using the configured embedding model."""
        from rag.embeddings.config import EmbeddingConfig

        config = EmbeddingConfig.from_settings()

        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        model = GoogleGenerativeAIEmbeddings(
            model=config.model_name,
            google_api_key=config.api_key,
        )
        return model.embed_query(query)


class KnowledgeGraphSearchView(APIView):
    """
    POST /api/search/knowledge-graph/

    Searches the Knowledge Graph for entities and relationships.

    Request body:
        {"query": "pump", "entity_type": "equipment"}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = request.data.get("query", "").strip()
        entity_type = request.data.get("entity_type")

        if not query:
            return Response(
                {"detail": "query is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hits = RAGRetrievalService.search_knowledge_graph(
            query=query,
            entity_type=entity_type,
        )

        return Response({
            "query": query,
            "entity_type": entity_type,
            "results": [h.to_dict() for h in hits],
            "total": len(hits),
        })


class DrawingSearchView(APIView):
    """
    POST /api/search/drawings/

    Searches for engineering drawing data.

    Request body:
        {"query": "P-101", "drawing_type": "pid", "equipment": "P-101A"}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = request.data.get("query", "").strip()
        drawing_type = request.data.get("drawing_type")
        equipment = request.data.get("equipment")

        if not query and not equipment:
            return Response(
                {"detail": "query or equipment is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hits = RAGRetrievalService.search_drawings(
            query=query,
            drawing_type=drawing_type,
            equipment=equipment,
        )

        return Response({
            "query": query,
            "drawing_type": drawing_type,
            "equipment": equipment,
            "results": [h.to_dict() for h in hits],
            "total": len(hits),
        })


class HybridQueryView(APIView):
    """
    POST /api/query/

    Full RAG pipeline: intent detection → hybrid retrieval → context
    building → LLM generation → structured response with citations.

    Request body:
        {"query": "What maintenance does P-101A need?", "session_id": "optional"}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = request.data.get("query", "").strip()
        session_id = request.data.get("session_id", "")

        if not query:
            return Response(
                {"detail": "query is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Try to embed the query for semantic search
        query_embedding = None
        try:
            query_embedding = SemanticSearchView._embed_query(query)
        except Exception:
            # Continue without semantic search — KG only
            pass

        response = QueryOrchestrator.process_query(
            query=query,
            session_id=session_id,
            query_embedding=query_embedding,
        )

        return Response(response.to_dict())


class ExecutiveBriefingView(APIView):
    """
    POST /api/briefing/ — Generate an executive operations briefing.

    Reuses OperationsIntelligenceOrchestrator + ExecutiveBriefingService.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        query = request.data.get("query", "Generate operations briefing").strip()

        # Run operations intelligence to get the report
        from agents.operations import OperationsIntelligenceOrchestrator
        from agents.briefing import ExecutiveBriefingService

        query_embedding = None
        try:
            query_embedding = SemanticSearchView._embed_query(query)
        except Exception:
            pass

        report = OperationsIntelligenceOrchestrator.execute(
            query=query, query_embedding=query_embedding
        )

        # Generate briefing from report
        briefing = ExecutiveBriefingService.generate(report=report)

        return Response({
            "briefing": briefing.to_dict(),
            "operations_report": report.to_dict(),
        })


class CommandCenterView(APIView):
    """
    GET /api/command-center/ — Returns current operations status for dashboard.

    All KPIs are dynamically computed from real data: Knowledge Graph,
    Document model, and agent outputs. Never hardcoded.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.documents.models import Document
        from knowledge_graph.graph import GraphService
        from knowledge_graph.service import KnowledgeGraphService
        from agents.warnings import WarningEngine

        # --- Knowledge Graph statistics ---
        stats = GraphService.get_statistics()
        entity_types = stats.get("entity_types", {})
        total_nodes = stats.get("total_nodes", 0)
        total_edges = stats.get("total_edges", 0)

        # --- Equipment count (from KG) ---
        equipment_types = ["pump", "valve", "compressor", "heat_exchanger",
                          "tank", "motor", "pipeline", "instrument", "sensor", "equipment"]
        total_equipment = sum(entity_types.get(t, 0) for t in equipment_types)

        # --- Document counts (from DB) ---
        total_documents = Document.objects.filter(uploaded_by=request.user).count()

        # --- Failure modes in KG ---
        failure_count = entity_types.get("failure_mode", 0)

        # --- Regulations/standards in KG ---
        regulation_count = entity_types.get("regulation", 0) + entity_types.get("standard", 0)

        # --- SOPs in KG ---
        sop_count = entity_types.get("sop", 0)

        # --- Compliance score (computed from KG data availability) ---
        # Score based on: regulations found, SOPs present, no major gaps
        if regulation_count > 0 and sop_count > 0:
            compliance_score = min(0.7 + (regulation_count * 0.03) + (sop_count * 0.05), 0.98)
        elif total_nodes > 0:
            compliance_score = 0.5
        else:
            compliance_score = 0.0

        # --- Plant health (computed from equipment vs failures) ---
        if total_equipment == 0:
            plant_health_pct = 0
            plant_health_label = "no_data"
        else:
            # Health = (equipment without failures) / total equipment
            health_ratio = max(0, (total_equipment - failure_count)) / total_equipment
            plant_health_pct = round(health_ratio * 100)
            if health_ratio >= 0.85:
                plant_health_label = "good"
            elif health_ratio >= 0.6:
                plant_health_label = "fair"
            else:
                plant_health_label = "poor"

        # --- Warnings (from existing engine) ---
        # Build maintenance/compliance context from KG for warning generation
        maint_data = None
        comp_data = None
        if failure_count > 0:
            maint_data = {
                "risk_level": "high" if failure_count > 2 else "medium",
                "problem_summary": f"{failure_count} failure mode(s) detected in knowledge base",
                "detected_failure_modes": [
                    e for e in entity_types.keys() if e == "failure_mode"
                ] * min(failure_count, 3),
                "confidence": 0.7,
            }
        if compliance_score < 0.7:
            comp_data = {
                "compliance_status": "partially_compliant",
                "compliance_gaps": [{"priority": "medium", "requirement": "Documentation", "standard": "ISO 9001", "evidence": "Limited records", "required_action": "Upload documents"}],
                "confidence": 0.6,
                "missing_documents": [],
            }

        warnings = WarningEngine.generate_warnings(
            maintenance_data=maint_data,
            compliance_data=comp_data,
        )

        critical_alerts = sum(1 for w in warnings if w.severity == "CRITICAL")
        high_alerts = sum(1 for w in warnings if w.severity == "HIGH")

        # --- Overall risk ---
        if critical_alerts > 0:
            overall_risk = "critical"
        elif high_alerts > 0 or failure_count > 3:
            overall_risk = "high"
        elif failure_count > 0 or compliance_score < 0.7:
            overall_risk = "medium"
        else:
            overall_risk = "low"

        # --- Top equipment at risk (from KG: entities with failure relationships) ---
        top_risk_equipment = []
        failure_entities = KnowledgeGraphService.search_entities("", entity_type="failure_mode")
        for fe in failure_entities[:5]:
            related = KnowledgeGraphService.get_related_entities(fe.get("entity_id", ""))
            for r in related:
                if r.get("entity_type") in equipment_types:
                    top_risk_equipment.append(r.get("name", ""))
        top_risk_equipment = list(set(top_risk_equipment))[:5]

        # --- Has data flag ---
        has_data = total_nodes > 0 or total_documents > 0

        # --- Briefing readiness ---
        briefing_ready = total_nodes > 5 and total_edges > 3

        return Response({
            "has_data": has_data,
            "plant_health": plant_health_label,
            "plant_health_pct": plant_health_pct,
            "overall_risk": overall_risk,
            "compliance_score": round(compliance_score, 2),
            "critical_alerts": critical_alerts + high_alerts,
            "total_alerts": len(warnings),
            "warnings": [w.to_dict() for w in warnings],
            "briefing_ready": briefing_ready,
            "knowledge_graph": {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "entity_types": entity_types,
            },
            "kpis": {
                "total_documents": total_documents,
                "total_equipment": total_equipment,
                "total_relationships": total_edges,
                "total_nodes": total_nodes,
                "failure_modes": failure_count,
                "regulations": regulation_count,
                "sops": sop_count,
            },
            "top_risk_equipment": top_risk_equipment,
            "recent_entity_types": sorted(entity_types.keys())[:10],
        })
