"""
Dashboard application for IndusMind AI.

Presents the authenticated enterprise workspace: overview dashboard,
document summaries, processing pipeline status, activity feed, and system
health. This app is currently presentation-only — it renders static,
representative context data. It contains no authentication, no database
models, and no live integration with ingestion/RAG/knowledge-graph
services; those integrations will replace the static context data in
`views.py` once the corresponding backend modules exist.
"""
