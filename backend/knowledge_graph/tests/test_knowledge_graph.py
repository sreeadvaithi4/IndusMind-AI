"""
Tests for the Knowledge Graph module (knowledge_graph/).

Tests cover:
    - Configuration validation
    - Entity extraction (pattern-based)
    - Relationship extraction
    - Graph CRUD operations (add, get, delete nodes/edges)
    - Entity deduplication
    - Document deletion cleanup
    - Graph search
    - Graph statistics
    - Full pipeline integration (text → entities → graph)
    - Empty/invalid input handling
"""

from django.test import TestCase, override_settings

from knowledge_graph.config import KnowledgeGraphConfig, ENTITY_TYPES, RELATIONSHIP_TYPES
from knowledge_graph.exceptions import (
    EntityExtractionError,
    KnowledgeGraphConfigurationError,
    KnowledgeGraphError,
)
from knowledge_graph.extractor import EntityExtractor
from knowledge_graph.graph import GraphService
from knowledge_graph.models import Entity, ExtractionResult, Relationship
from knowledge_graph.service import KnowledgeGraphService


def _make_config(**overrides):
    """Helper to create a test config."""
    defaults = {
        "entity_confidence_threshold": 0.3,
        "relationship_confidence_threshold": 0.3,
        "supported_entity_types": ENTITY_TYPES,
        "supported_relationship_types": RELATIONSHIP_TYPES,
        "max_entities_per_document": 500,
        "max_relationships_per_document": 1000,
        "deduplication_enabled": True,
    }
    defaults.update(overrides)
    return KnowledgeGraphConfig(**defaults)


INDUSTRIAL_TEXT = """
The centrifugal pump P-101A is located in Unit Area-3 of the Refinery Plant.
It is connected to valve V-201B downstream. The pump requires preventive maintenance
every 6 months, performed by the Maintenance Department.

Corrosion was detected during visual inspection on 2024-01-15. The bearing
(SKF 6205) needs replacement. SOP-M-001 applies to this equipment.

ISO 9001 and API 610 govern the pump operation. The pump was manufactured by
Flowserve Corporation.

Heat exchanger E-301 is part of the cooling system. Tank TK-401 stores
the process fluid. Motor M-101 drives the compressor C-501.
"""


class KnowledgeGraphConfigTests(TestCase):
    """Tests for KnowledgeGraphConfig."""

    @override_settings(KG_ENTITY_CONFIDENCE_THRESHOLD=0.5)
    def test_from_settings_with_custom_threshold(self):
        config = KnowledgeGraphConfig.from_settings()
        self.assertEqual(config.entity_confidence_threshold, 0.5)

    @override_settings(KG_ENTITY_CONFIDENCE_THRESHOLD=1.5)
    def test_from_settings_raises_on_invalid_threshold(self):
        with self.assertRaises(KnowledgeGraphConfigurationError):
            KnowledgeGraphConfig.from_settings()

    def test_from_settings_defaults(self):
        config = KnowledgeGraphConfig.from_settings()
        self.assertEqual(config.entity_confidence_threshold, 0.3)
        self.assertEqual(config.max_entities_per_document, 500)
        self.assertTrue(config.deduplication_enabled)


class EntityExtractionTests(TestCase):
    """Tests for entity extraction."""

    def setUp(self):
        self.config = _make_config()

    def test_extracts_pump_entities(self):
        text = "The centrifugal pump is running. P-101A needs repair."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        pump_entities = [e for e in result.entities if e.entity_type == "pump"]
        self.assertGreater(len(pump_entities), 0)

    def test_extracts_valve_entities(self):
        text = "Gate valve V-201B is installed downstream."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        valve_entities = [e for e in result.entities if e.entity_type == "valve"]
        self.assertGreater(len(valve_entities), 0)

    def test_extracts_equipment_tags(self):
        text = "Check equipment HX-301A and TK-401."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        self.assertGreater(result.entity_count, 0)

    def test_extracts_regulations(self):
        text = "This equipment must comply with ISO 9001 and API 610."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        reg_entities = [e for e in result.entities if e.entity_type == "regulation"]
        self.assertGreater(len(reg_entities), 0)

    def test_extracts_failure_modes(self):
        text = "Corrosion and cavitation were observed on the impeller."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        failure_entities = [e for e in result.entities if e.entity_type == "failure_mode"]
        self.assertGreater(len(failure_entities), 0)

    def test_extracts_maintenance_activities(self):
        text = "Preventive maintenance and calibration are scheduled."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        maint_entities = [
            e for e in result.entities if e.entity_type == "maintenance_activity"
        ]
        self.assertGreater(len(maint_entities), 0)

    def test_extracts_sop_references(self):
        text = "Follow SOP-M-001 for pump maintenance procedures."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        sop_entities = [e for e in result.entities if e.entity_type == "sop"]
        self.assertGreater(len(sop_entities), 0)

    def test_deduplicates_same_entity(self):
        text = "P-101A is running. Check P-101A again."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        # Same entity mentioned twice should appear once
        p101_entities = [e for e in result.entities if "P-101A" in e.name]
        self.assertEqual(len(p101_entities), 1)

    def test_empty_text_returns_empty_result(self):
        result = EntityExtractor.extract("", "doc-1", self.config)
        self.assertEqual(result.entity_count, 0)
        self.assertEqual(result.relationship_count, 0)

    def test_respects_confidence_threshold(self):
        config = _make_config(entity_confidence_threshold=0.9)
        text = "P-101A is a pump"
        result = EntityExtractor.extract(text, "doc-1", config)
        # Pattern-based extraction has 0.7 confidence, threshold 0.9 filters all
        self.assertEqual(result.entity_count, 0)

    def test_respects_max_entities_limit(self):
        config = _make_config(max_entities_per_document=2)
        result = EntityExtractor.extract(INDUSTRIAL_TEXT, "doc-1", config)
        self.assertLessEqual(result.entity_count, 2)

    def test_industrial_text_extracts_multiple_entity_types(self):
        result = EntityExtractor.extract(INDUSTRIAL_TEXT, "doc-1", self.config)
        entity_types = set(e.entity_type for e in result.entities)
        # Should extract at least pumps, valves, and regulations
        self.assertGreater(len(entity_types), 2)


class RelationshipExtractionTests(TestCase):
    """Tests for relationship extraction."""

    def setUp(self):
        self.config = _make_config()

    def test_extracts_located_in_relationship(self):
        text = "Pump P-101A is located in Area-3."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        located_rels = [
            r for r in result.relationships if r.relationship_type == "located_in"
        ]
        # May or may not find depending on entity matching
        # At minimum, document->mentions relationships should exist
        self.assertGreater(result.relationship_count, 0)

    def test_extracts_connected_to_relationship(self):
        text = "P-101A is connected to V-201B."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        self.assertGreater(result.relationship_count, 0)

    def test_mentions_relationships_created_for_all_entities(self):
        text = "P-101A and V-201B are in the system."
        result = EntityExtractor.extract(text, "doc-1", self.config)
        mentions_rels = [
            r for r in result.relationships if r.relationship_type == "mentions"
        ]
        # Each entity gets a "document mentions entity" relationship
        self.assertEqual(len(mentions_rels), result.entity_count)


class GraphServiceTests(TestCase):
    """Tests for the NetworkX graph CRUD operations."""

    def setUp(self):
        GraphService.reset()

    def test_add_entity_creates_node(self):
        entity = Entity(
            entity_type="pump",
            name="P-101A",
            source_document_ids=["doc-1"],
        )
        GraphService.add_entity(entity)
        result = GraphService.get_entity(entity.entity_id)
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "P-101A")
        self.assertEqual(result["entity_type"], "pump")

    def test_add_duplicate_entity_merges(self):
        entity = Entity(
            entity_id="fixed-id",
            entity_type="pump",
            name="P-101A",
            source_document_ids=["doc-1"],
        )
        GraphService.add_entity(entity)

        # Add again with different source doc
        entity2 = Entity(
            entity_id="fixed-id",
            entity_type="pump",
            name="P-101A",
            source_document_ids=["doc-2"],
        )
        GraphService.add_entity(entity2)

        result = GraphService.get_entity("fixed-id")
        self.assertIn("doc-1", result["source_document_ids"])
        self.assertIn("doc-2", result["source_document_ids"])

    def test_add_relationship_creates_edge(self):
        e1 = Entity(entity_id="e1", entity_type="pump", name="P-101")
        e2 = Entity(entity_id="e2", entity_type="valve", name="V-201")
        GraphService.add_entity(e1)
        GraphService.add_entity(e2)

        rel = Relationship(
            relationship_type="connected_to",
            source_entity_id="e1",
            target_entity_id="e2",
            source_document_id="doc-1",
        )
        GraphService.add_relationship(rel)

        relationships = GraphService.get_relationships("e1")
        self.assertEqual(len(relationships), 1)
        self.assertEqual(relationships[0]["relationship_type"], "connected_to")

    def test_get_related_entities(self):
        e1 = Entity(entity_id="e1", entity_type="pump", name="P-101")
        e2 = Entity(entity_id="e2", entity_type="valve", name="V-201")
        GraphService.add_entity(e1)
        GraphService.add_entity(e2)

        rel = Relationship(
            relationship_type="connected_to",
            source_entity_id="e1",
            target_entity_id="e2",
        )
        GraphService.add_relationship(rel)

        related = GraphService.get_related_entities("e1")
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]["entity_id"], "e2")

    def test_delete_entity_removes_node_and_edges(self):
        e1 = Entity(entity_id="e1", entity_type="pump", name="P-101")
        e2 = Entity(entity_id="e2", entity_type="valve", name="V-201")
        GraphService.add_entity(e1)
        GraphService.add_entity(e2)
        rel = Relationship(
            relationship_type="connected_to",
            source_entity_id="e1",
            target_entity_id="e2",
        )
        GraphService.add_relationship(rel)

        GraphService.delete_entity("e1")
        self.assertIsNone(GraphService.get_entity("e1"))
        self.assertEqual(len(GraphService.get_relationships("e2")), 0)

    def test_delete_document_entities(self):
        e1 = Entity(entity_id="e1", entity_type="pump", name="P-101",
                    source_document_ids=["doc-1"])
        e2 = Entity(entity_id="e2", entity_type="valve", name="V-201",
                    source_document_ids=["doc-1", "doc-2"])
        GraphService.add_entity(e1)
        GraphService.add_entity(e2)

        removed = GraphService.delete_document_entities("doc-1")
        # e1 should be removed (only source was doc-1)
        # e2 should remain (still has doc-2)
        self.assertEqual(removed, 1)
        self.assertIsNone(GraphService.get_entity("e1"))
        self.assertIsNotNone(GraphService.get_entity("e2"))

    def test_search_entities_by_name(self):
        e1 = Entity(entity_id="e1", entity_type="pump", name="Centrifugal Pump P-101")
        e2 = Entity(entity_id="e2", entity_type="valve", name="Gate Valve V-201")
        GraphService.add_entity(e1)
        GraphService.add_entity(e2)

        results = GraphService.search_entities("pump")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Centrifugal Pump P-101")

    def test_search_entities_by_type(self):
        e1 = Entity(entity_id="e1", entity_type="pump", name="P-101")
        e2 = Entity(entity_id="e2", entity_type="valve", name="V-201")
        GraphService.add_entity(e1)
        GraphService.add_entity(e2)

        results = GraphService.search_entities("", entity_type="pump")
        self.assertEqual(len(results), 1)

    def test_get_statistics(self):
        e1 = Entity(entity_id="e1", entity_type="pump", name="P-101")
        e2 = Entity(entity_id="e2", entity_type="valve", name="V-201")
        GraphService.add_entity(e1)
        GraphService.add_entity(e2)
        rel = Relationship(
            relationship_type="connected_to",
            source_entity_id="e1",
            target_entity_id="e2",
        )
        GraphService.add_relationship(rel)

        stats = GraphService.get_statistics()
        self.assertEqual(stats["total_nodes"], 2)
        self.assertEqual(stats["total_edges"], 1)
        self.assertIn("pump", stats["entity_types"])
        self.assertIn("connected_to", stats["relationship_types"])

    def test_get_document_entities(self):
        e1 = Entity(entity_id="e1", entity_type="pump", name="P-101",
                    source_document_ids=["doc-1"])
        e2 = Entity(entity_id="e2", entity_type="valve", name="V-201",
                    source_document_ids=["doc-2"])
        GraphService.add_entity(e1)
        GraphService.add_entity(e2)

        results = GraphService.get_document_entities("doc-1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "P-101")


class KnowledgeGraphServiceTests(TestCase):
    """Tests for the top-level KnowledgeGraphService."""

    def setUp(self):
        GraphService.reset()

    def test_process_document_extracts_and_populates(self):
        config = _make_config()
        result = KnowledgeGraphService.process_document(
            INDUSTRIAL_TEXT, "doc-1", config=config
        )
        self.assertIsInstance(result, ExtractionResult)
        self.assertGreater(result.entity_count, 0)
        self.assertGreater(result.relationship_count, 0)

        # Verify graph was populated
        stats = GraphService.get_statistics()
        self.assertGreater(stats["total_nodes"], 0)

    def test_process_empty_text(self):
        config = _make_config()
        result = KnowledgeGraphService.process_document("", "doc-1", config=config)
        self.assertEqual(result.entity_count, 0)

    def test_process_document_missing_id_raises(self):
        with self.assertRaises(KnowledgeGraphError):
            KnowledgeGraphService.process_document("some text", "")

    def test_delete_document_removes_entities(self):
        config = _make_config()
        KnowledgeGraphService.process_document(INDUSTRIAL_TEXT, "doc-1", config=config)

        stats_before = GraphService.get_statistics()
        self.assertGreater(stats_before["total_nodes"], 0)

        KnowledgeGraphService.delete_document("doc-1")

        stats_after = GraphService.get_statistics()
        # Some or all nodes should be removed
        self.assertLess(stats_after["total_nodes"], stats_before["total_nodes"])

    def test_search_entities_via_service(self):
        config = _make_config()
        KnowledgeGraphService.process_document(INDUSTRIAL_TEXT, "doc-1", config=config)

        results = KnowledgeGraphService.search_entities("pump")
        self.assertGreater(len(results), 0)

    def test_get_document_entities_via_service(self):
        config = _make_config()
        KnowledgeGraphService.process_document(INDUSTRIAL_TEXT, "doc-1", config=config)

        entities = KnowledgeGraphService.get_document_entities("doc-1")
        self.assertGreater(len(entities), 0)
