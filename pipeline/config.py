import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass
class PipelineConfig:
    # National Law Information Center Open API
    law_api_key: str = field(default_factory=lambda: os.environ["LAW_API_KEY"])
    law_api_base_url: str = "https://www.law.go.kr/DRF"

    # Neo4j connection
    # Local Docker: bolt://localhost:7687
    # AuraDB:       neo4j+s://<instance-id>.databases.neo4j.io
    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "ordinance-password"))

    # Google Generative AI (for embeddings)
    google_api_key: str = field(default_factory=lambda: os.environ["GOOGLE_API_KEY"])

    # Embedding settings
    embedding_model: str = "models/gemini-embedding-001"
    embedding_dimensions: int = 3072
    embedding_batch_size: int = 20        # items per batch (rate limit safety)
    embedding_request_delay: float = 1.0  # seconds between batches
    similar_to_threshold: float = 0.8     # cosine similarity threshold for SIMILAR_TO

    # API pagination
    api_display_count: int = 100   # max results per request
    api_request_delay: float = 0.5  # seconds between requests (rate limit)

    # Domain keywords for filtered initial load
    domain_keywords: list[str] = field(default_factory=lambda: [
        "청년", "창업", "기업지원", "소상공인",
        "중소기업", "스타트업", "일자리", "보조금",
        "지방자치", "산업단지", "규제특례",
    ])

    # Core statutes always loaded regardless of keyword matching
    mandatory_statutes: list[str] = field(default_factory=lambda: [
        "지방자치법",
        "청년기본법",
        "보조금 관리에 관한 법률",
        "지방재정법",
        "중소기업 창업 지원법",
        "소상공인 보호 및 지원에 관한 법률",
    ])


config = PipelineConfig()
