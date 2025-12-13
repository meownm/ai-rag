# Пример: прямой анализ pgvector из Phoenix SDK
import phoenix as px
from sqlalchemy import create_engine
from phoenix.session.evaluation import VectorEvaluator

PG_URL = "postgresql+psycopg2://phoenix_ro:phoenix_password@localhost:5432/observability"

engine = create_engine(PG_URL)
evaluator = VectorEvaluator.from_pgvector(
    engine, table="chunks", id_col="id", text_col="content", vector_col="embedding"
)

# Базовые проверки распределения и качества
evaluator.inspect_vectors(limit=200)
