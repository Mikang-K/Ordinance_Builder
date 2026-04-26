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

    # Per-type keyword map for targeted loading via type_load.py
    ordinance_type_keywords: dict[str, list[str]] = field(default_factory=lambda: {
        "지원": [
            "청년", "창업", "기업지원", "소상공인",
            "중소기업", "스타트업", "일자리", "보조금",
            "지방자치", "산업단지", "규제특례",
        ],
        "설치·운영": [
            "위원회", "센터설치", "기관설립", "협의회",
            "자문위원회", "심의위원회", "지원센터",
            "조정위원회", "운영위원회", "지방공기업",
        ],
        "관리·규제": [
            "공유재산", "시설관리", "사용허가", "도로점용",
            "하천점용", "공원관리", "과태료",
            "사용료", "행정제재", "허가취소",
        ],
        "복지·서비스": [
            "사회서비스", "돌봄", "노인복지", "장애인복지",
            "아동복지", "청소년복지", "여성복지",
            "기초생활", "복지급여", "방문서비스",
        ],
    })

    # Per-type mandatory statutes for type_load.py
    mandatory_statutes_by_type: dict[str, list[str]] = field(default_factory=lambda: {
        "지원": [
            "지방자치법",
            "청년기본법",
            "보조금 관리에 관한 법률",
            "지방재정법",
            "중소기업 창업 지원법",
            "소상공인 보호 및 지원에 관한 법률",
        ],
        "설치·운영": [
            "지방자치단체 출자·출연 기관의 운영에 관한 법률",
            "공공기관의 운영에 관한 법률",
            "행정기관 소속 위원회의 설치·운영에 관한 법률",
        ],
        "관리·규제": [
            "공유재산 및 물품 관리법",
            "도로법",
            "하천법",
            "공중위생관리법",
        ],
        "복지·서비스": [
            "사회보장기본법",
            "노인복지법",
            "장애인복지법",
            "아동복지법",
            "사회서비스 이용 및 이용권 관리에 관한 법률",
        ],
    })


config = PipelineConfig()
