"""
Management command to load demo data into the Knowledge Graph.

Populates the KG with realistic industrial entities and relationships
so the dashboard and AI agents have data to work with on first run.

Usage: python manage.py load_demo_data
"""

from django.core.management.base import BaseCommand

from knowledge_graph.graph import GraphService
from knowledge_graph.models import Entity, Relationship


DEMO_ENTITIES = [
    Entity(entity_id="pump-001", entity_type="pump", name="Centrifugal Pump P-101A", source_document_ids=["demo"], confidence=0.9, metadata={"drawing_type": "pid", "source": "demo"}),
    Entity(entity_id="pump-002", entity_type="pump", name="Booster Pump P-201B", source_document_ids=["demo"], confidence=0.85),
    Entity(entity_id="valve-001", entity_type="valve", name="Control Valve FV-101", source_document_ids=["demo"], confidence=0.9, metadata={"drawing_type": "pid"}),
    Entity(entity_id="valve-002", entity_type="valve", name="Gate Valve V-201B", source_document_ids=["demo"], confidence=0.85),
    Entity(entity_id="valve-003", entity_type="valve", name="Relief Valve RV-301", source_document_ids=["demo"], confidence=0.8),
    Entity(entity_id="tank-001", entity_type="tank", name="Storage Tank TK-201", source_document_ids=["demo"], confidence=0.9),
    Entity(entity_id="tank-002", entity_type="tank", name="Surge Tank TK-301", source_document_ids=["demo"], confidence=0.85),
    Entity(entity_id="comp-001", entity_type="compressor", name="Gas Compressor C-501", source_document_ids=["demo"], confidence=0.9),
    Entity(entity_id="hx-001", entity_type="heat_exchanger", name="Shell & Tube HX E-301", source_document_ids=["demo"], confidence=0.9),
    Entity(entity_id="motor-001", entity_type="motor", name="Electric Motor M-101", source_document_ids=["demo"], confidence=0.85),
    Entity(entity_id="inst-001", entity_type="instrument", name="Pressure Transmitter PT-101", source_document_ids=["demo"], confidence=0.9),
    Entity(entity_id="inst-002", entity_type="instrument", name="Temperature Transmitter TT-201", source_document_ids=["demo"], confidence=0.85),
    Entity(entity_id="inst-003", entity_type="instrument", name="Flow Transmitter FT-301", source_document_ids=["demo"], confidence=0.85),
    Entity(entity_id="plant-001", entity_type="plant", name="Refinery Unit 3", source_document_ids=["demo"], confidence=0.95),
    Entity(entity_id="area-001", entity_type="area", name="Process Area A", source_document_ids=["demo"], confidence=0.9),
    Entity(entity_id="area-002", entity_type="area", name="Utility Area B", source_document_ids=["demo"], confidence=0.9),
    Entity(entity_id="dept-001", entity_type="department", name="Maintenance Department", source_document_ids=["demo"], confidence=0.95),
    Entity(entity_id="reg-001", entity_type="regulation", name="ISO 9001:2015", source_document_ids=["demo"], confidence=0.95),
    Entity(entity_id="reg-002", entity_type="regulation", name="API 610", source_document_ids=["demo"], confidence=0.9),
    Entity(entity_id="reg-003", entity_type="regulation", name="ASME B31.3", source_document_ids=["demo"], confidence=0.9),
    Entity(entity_id="sop-001", entity_type="sop", name="SOP-M-001 Pump Maintenance", source_document_ids=["demo"], confidence=0.9),
    Entity(entity_id="sop-002", entity_type="sop", name="SOP-I-002 Instrument Calibration", source_document_ids=["demo"], confidence=0.85),
    Entity(entity_id="fail-001", entity_type="failure_mode", name="Bearing Wear", source_document_ids=["demo"], confidence=0.8),
    Entity(entity_id="fail-002", entity_type="failure_mode", name="Seal Leakage", source_document_ids=["demo"], confidence=0.8),
    Entity(entity_id="fail-003", entity_type="failure_mode", name="Corrosion", source_document_ids=["demo"], confidence=0.8),
]

DEMO_RELATIONSHIPS = [
    Relationship(relationship_type="located_in", source_entity_id="pump-001", target_entity_id="area-001", source_document_id="demo"),
    Relationship(relationship_type="located_in", source_entity_id="tank-001", target_entity_id="area-001", source_document_id="demo"),
    Relationship(relationship_type="located_in", source_entity_id="comp-001", target_entity_id="area-002", source_document_id="demo"),
    Relationship(relationship_type="connected_to", source_entity_id="pump-001", target_entity_id="valve-001", source_document_id="demo"),
    Relationship(relationship_type="connected_to", source_entity_id="valve-001", target_entity_id="tank-001", source_document_id="demo"),
    Relationship(relationship_type="connected_to", source_entity_id="pump-002", target_entity_id="valve-002", source_document_id="demo"),
    Relationship(relationship_type="connected_to", source_entity_id="hx-001", target_entity_id="valve-003", source_document_id="demo"),
    Relationship(relationship_type="part_of", source_entity_id="area-001", target_entity_id="plant-001", source_document_id="demo"),
    Relationship(relationship_type="part_of", source_entity_id="area-002", target_entity_id="plant-001", source_document_id="demo"),
    Relationship(relationship_type="maintained_by", source_entity_id="pump-001", target_entity_id="dept-001", source_document_id="demo"),
    Relationship(relationship_type="maintained_by", source_entity_id="comp-001", target_entity_id="dept-001", source_document_id="demo"),
    Relationship(relationship_type="governs", source_entity_id="reg-001", target_entity_id="pump-001", source_document_id="demo"),
    Relationship(relationship_type="governs", source_entity_id="reg-002", target_entity_id="pump-001", source_document_id="demo"),
    Relationship(relationship_type="governs", source_entity_id="reg-003", target_entity_id="hx-001", source_document_id="demo"),
    Relationship(relationship_type="applies_to", source_entity_id="sop-001", target_entity_id="pump-001", source_document_id="demo"),
    Relationship(relationship_type="applies_to", source_entity_id="sop-002", target_entity_id="inst-001", source_document_id="demo"),
    Relationship(relationship_type="monitors", source_entity_id="inst-001", target_entity_id="pump-001", source_document_id="demo"),
    Relationship(relationship_type="monitors", source_entity_id="inst-002", target_entity_id="tank-001", source_document_id="demo"),
    Relationship(relationship_type="monitors", source_entity_id="inst-003", target_entity_id="hx-001", source_document_id="demo"),
    Relationship(relationship_type="affects", source_entity_id="fail-001", target_entity_id="pump-001", source_document_id="demo"),
    Relationship(relationship_type="affects", source_entity_id="fail-002", target_entity_id="pump-001", source_document_id="demo"),
    Relationship(relationship_type="affects", source_entity_id="fail-003", target_entity_id="hx-001", source_document_id="demo"),
]


class Command(BaseCommand):
    help = "Loads demo industrial data into the Knowledge Graph"

    def handle(self, *args, **options):
        self.stdout.write("Loading demo data into Knowledge Graph...")

        for entity in DEMO_ENTITIES:
            GraphService.add_entity(entity)

        for rel in DEMO_RELATIONSHIPS:
            GraphService.add_relationship(rel)

        GraphService._persist()

        stats = GraphService.get_statistics()
        self.stdout.write(self.style.SUCCESS(
            f"✓ Loaded {stats['total_nodes']} entities and "
            f"{stats['total_edges']} relationships into the Knowledge Graph."
        ))
        self.stdout.write(self.style.SUCCESS(
            "  Entity types: " + ", ".join(f"{k}({v})" for k, v in sorted(stats['entity_types'].items()))
        ))
