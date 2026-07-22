# knowledge_graph/

Enterprise Knowledge Graph for IndusMind AI — entity extraction and
graph construction using NetworkX.

## Implemented (Sprint 9)

### Entity Extraction (`extractor.py`)

Pattern-based extraction using compiled regex for 30+ industrial entity
types including:
- Equipment (pumps, valves, compressors, heat exchangers, tanks, motors)
- Infrastructure (plants, areas, buildings, departments, pipelines)
- Procedures (SOPs, maintenance activities, inspection activities)
- Standards (ISO, API, ASME, OSHA, NFPA, ASTM, ANSI)
- Failures (failure modes, root causes, corrective/preventive actions)
- Components (spare parts, instruments, sensors, tags)

### Relationship Extraction

Automatically identifies 20+ relationship types:
- located_in, connected_to, part_of, installed_in
- maintained_by, operated_by, inspected_by
- affects, caused_by, resolves
- applies_to, governs, requires
- manufactured_by, replaced_by, references, mentions

### Graph Service (`graph.py`)

NetworkX-backed directed graph with:
- Node CRUD (add, get, update, delete entities)
- Edge CRUD (add, get relationships)
- Entity deduplication (merge on same ID)
- Document cleanup (remove entities when document is deleted)
- Search by name/alias (case-insensitive substring)
- Filter by entity type
- Traversal (get related entities, get relationships)
- Statistics (node/edge counts by type)
- Pickle persistence (configurable path)

### Entry Point (`service.py`)

`KnowledgeGraphService.process_document(text, document_id)` — extracts
entities and relationships, populates the graph, returns ExtractionResult.

## Configuration

Via Django settings / environment variables:
- `KG_ENTITY_CONFIDENCE_THRESHOLD` (default: 0.3)
- `KG_RELATIONSHIP_CONFIDENCE_THRESHOLD` (default: 0.3)
- `KG_MAX_ENTITIES_PER_DOCUMENT` (default: 500)
- `KG_MAX_RELATIONSHIPS_PER_DOCUMENT` (default: 1000)
- `KG_DEDUPLICATION_ENABLED` (default: True)
- `KG_PERSIST_PATH` (default: knowledge_graph.pkl)
