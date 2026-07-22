"""
Django settings for the IndusMind AI project.

This module follows the 12-factor app methodology: all environment-specific
configuration (secrets, database URLs, debug flags, API keys) is read from
environment variables via django-environ, with sane local-development
defaults. No environment-specific values are hardcoded here.

Production readiness:
    - SQLite is used by default for local development.
    - Setting the DATABASE_URL environment variable switches to PostgreSQL
      (or any other database supported by dj-database-url syntax) without
      any code changes.
"""

from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# BASE_DIR points to backend/ (the Django project root, containing manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# PROJECT_ROOT points to the repository root (one level above backend/)
PROJECT_ROOT = BASE_DIR.parent

# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
)

# Read .env from the project root if present. Environment variables set in
# the actual process environment always take precedence over the .env file.
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

# ---------------------------------------------------------------------------
# Core settings
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-insecure-secret-key")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
]

# Project-specific apps are registered here as they are built.
LOCAL_APPS: list[str] = [
    "apps.dashboard",
    "apps.documents",
    "apps.chat",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
LOGIN_URL = "/"
LOGIN_REDIRECT_URL = "/home/"
LOGOUT_REDIRECT_URL = "/"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Defaults to SQLite for local development. Set DATABASE_URL to switch to
# PostgreSQL (or another supported backend) for production without any
# code changes. An unset or blank DATABASE_URL both fall back to SQLite —
# django-environ only applies its `default=` when the variable is
# entirely absent, so a blank value (as shipped in .env.example) is
# normalized to the SQLite URL before parsing.
_database_url = env("DATABASE_URL", default="") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"

DATABASES = {
    "default": env.db_url_config(_database_url),
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files (CSS, JavaScript, Images)
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "static_collected"

# CompressedManifestStaticFilesStorage requires a manifest produced by
# `collectstatic`, so it is only safe to use once that manifest exists
# (production/deployment). In DEBUG (local development), fall back to
# WhiteNoise's non-manifest storage so `runserver` works without first
# running `collectstatic`.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

# ---------------------------------------------------------------------------
# Media files (user uploads, generated documents)
# ---------------------------------------------------------------------------
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Directory used for raw document ingestion uploads (distinct from Django's
# MEDIA_ROOT, which is reserved for served/user-facing media).
UPLOADS_ROOT = BASE_DIR / "uploads"

# ---------------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# AI / LLM configuration (IndusMind AI specific)
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = env("GOOGLE_API_KEY", default="")

# ---------------------------------------------------------------------------
# Vector database (ChromaDB) configuration
# ---------------------------------------------------------------------------
CHROMA_PERSIST_DIRECTORY = str(
    PROJECT_ROOT / env("CHROMA_PERSIST_DIRECTORY", default="chroma_db")
)
CHROMA_COLLECTION_NAME = env("CHROMA_COLLECTION_NAME", default="indusmind_documents")
CHROMA_BATCH_SIZE = env.int("CHROMA_BATCH_SIZE", default=100)
CHROMA_SEARCH_K = env.int("CHROMA_SEARCH_K", default=10)
CHROMA_SIMILARITY_THRESHOLD = env.float("CHROMA_SIMILARITY_THRESHOLD", default=0.0)
CHROMA_MAX_RESULTS = env.int("CHROMA_MAX_RESULTS", default=50)

# ---------------------------------------------------------------------------
# Knowledge Graph configuration
# ---------------------------------------------------------------------------
# All consumed via knowledge_graph.config.KnowledgeGraphConfig.from_settings().
KG_ENTITY_CONFIDENCE_THRESHOLD = env.float(
    "KG_ENTITY_CONFIDENCE_THRESHOLD", default=0.3
)
KG_RELATIONSHIP_CONFIDENCE_THRESHOLD = env.float(
    "KG_RELATIONSHIP_CONFIDENCE_THRESHOLD", default=0.3
)
KG_MAX_ENTITIES_PER_DOCUMENT = env.int("KG_MAX_ENTITIES_PER_DOCUMENT", default=500)
KG_MAX_RELATIONSHIPS_PER_DOCUMENT = env.int(
    "KG_MAX_RELATIONSHIPS_PER_DOCUMENT", default=1000
)
KG_DEDUPLICATION_ENABLED = env.bool("KG_DEDUPLICATION_ENABLED", default=True)
KG_PERSIST_PATH = str(
    PROJECT_ROOT / env("KG_PERSIST_PATH", default="knowledge_graph.pkl")
)

# ---------------------------------------------------------------------------
# Computer Vision / Drawing Analysis configuration
# ---------------------------------------------------------------------------
VISION_OCR_CONFIDENCE_THRESHOLD = env.float(
    "VISION_OCR_CONFIDENCE_THRESHOLD", default=0.3
)
VISION_SYMBOL_CONFIDENCE_THRESHOLD = env.float(
    "VISION_SYMBOL_CONFIDENCE_THRESHOLD", default=0.5
)
VISION_MAX_EQUIPMENT_PER_DRAWING = env.int(
    "VISION_MAX_EQUIPMENT_PER_DRAWING", default=200
)
VISION_MAX_RELATIONSHIPS_PER_DRAWING = env.int(
    "VISION_MAX_RELATIONSHIPS_PER_DRAWING", default=500
)

# ---------------------------------------------------------------------------
# RAG Pipeline / Agent Orchestrator configuration
# ---------------------------------------------------------------------------
RAG_TOP_K = env.int("RAG_TOP_K", default=10)
RAG_SIMILARITY_THRESHOLD = env.float("RAG_SIMILARITY_THRESHOLD", default=0.0)
RAG_MAX_CONTEXT_TOKENS = env.int("RAG_MAX_CONTEXT_TOKENS", default=4000)
RAG_MAX_RESPONSE_TOKENS = env.int("RAG_MAX_RESPONSE_TOKENS", default=2000)
RAG_LLM_MODEL = env("RAG_LLM_MODEL", default="gemini-1.5-flash")
RAG_TEMPERATURE = env.float("RAG_TEMPERATURE", default=0.3)
RAG_LLM_TIMEOUT_SECONDS = env.int("RAG_LLM_TIMEOUT_SECONDS", default=30)
RAG_LLM_MAX_RETRIES = env.int("RAG_LLM_MAX_RETRIES", default=3)
RAG_WEIGHT_SEMANTIC = env.float("RAG_WEIGHT_SEMANTIC", default=0.4)
RAG_WEIGHT_GRAPH = env.float("RAG_WEIGHT_GRAPH", default=0.25)
RAG_WEIGHT_METADATA = env.float("RAG_WEIGHT_METADATA", default=0.15)
RAG_WEIGHT_RECENCY = env.float("RAG_WEIGHT_RECENCY", default=0.1)
RAG_WEIGHT_CONFIDENCE = env.float("RAG_WEIGHT_CONFIDENCE", default=0.1)

# ---------------------------------------------------------------------------
# OCR configuration
# ---------------------------------------------------------------------------
TESSERACT_CMD = env("TESSERACT_CMD", default="")

# Hard on/off switch for OCR fallback during document parsing (see
# ingestion/ocr.py). Even when True, OCR is only actually attempted if
# pytesseract/Pillow/pdf2image are installed and text extraction
# appears to have failed — this flag lets operators disable OCR
# entirely (e.g. in environments without Tesseract installed) without
# uninstalling packages.
OCR_ENABLED = env.bool("OCR_ENABLED", default=True)

# ---------------------------------------------------------------------------
# Document chunking configuration
# ---------------------------------------------------------------------------
# All consumed via ingestion.chunking.config.ChunkingConfig.from_settings().
CHUNKING_CHUNK_SIZE = env.int("CHUNKING_CHUNK_SIZE", default=1000)
CHUNKING_CHUNK_OVERLAP = env.int("CHUNKING_CHUNK_OVERLAP", default=150)
CHUNKING_MAX_CHUNK_LENGTH = env.int("CHUNKING_MAX_CHUNK_LENGTH", default=2000)
CHUNKING_MIN_CHUNK_LENGTH = env.int("CHUNKING_MIN_CHUNK_LENGTH", default=20)

# ---------------------------------------------------------------------------
# Embedding Generator configuration
# ---------------------------------------------------------------------------
# All consumed via rag.embeddings.config.EmbeddingConfig.from_settings().
EMBEDDING_MODEL_NAME = env(
    "EMBEDDING_MODEL_NAME", default="models/embedding-001"
)
EMBEDDING_BATCH_SIZE = env.int("EMBEDDING_BATCH_SIZE", default=20)
EMBEDDING_MAX_RETRIES = env.int("EMBEDDING_MAX_RETRIES", default=3)
EMBEDDING_TIMEOUT_SECONDS = env.int("EMBEDDING_TIMEOUT_SECONDS", default=30)
EMBEDDING_MAX_CONCURRENT_REQUESTS = env.int(
    "EMBEDDING_MAX_CONCURRENT_REQUESTS", default=5
)
EMBEDDING_MAX_CHUNK_TEXT_LENGTH = env.int(
    "EMBEDDING_MAX_CHUNK_TEXT_LENGTH", default=10000
)

# ---------------------------------------------------------------------------
# Document upload configuration
# ---------------------------------------------------------------------------
# Maximum accepted upload size, in megabytes. Enforced by
# apps.documents.validators.validate_file_size.
DOCUMENT_MAX_UPLOAD_SIZE_MB = env.int("DOCUMENT_MAX_UPLOAD_SIZE_MB", default=50)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.documents": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "rag.embeddings": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "rag.vectorstore": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "knowledge_graph": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "vision": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "agents": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "agents.retrieval": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "agents.llm": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "agents.orchestrator": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "api": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
