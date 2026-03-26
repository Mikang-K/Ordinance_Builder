from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.core.config import settings

_embedder_instance: GoogleGenerativeAIEmbeddings | None = None


def get_embedder() -> GoogleGenerativeAIEmbeddings:
    """Return a singleton GoogleGenerativeAIEmbeddings instance."""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
        )
    return _embedder_instance
