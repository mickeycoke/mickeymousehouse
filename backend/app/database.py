from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/mickeymouse_house")

# Endpoints are sync `def`, so FastAPI runs each in its threadpool (default 40
# threads) and every in-flight request holds a DB connection for its whole
# duration — including serializing large responses. The old default pool
# (5 + 10 overflow = 15) sat far below that, so any burst past 15 concurrent
# requests starved the pool: the 16th+ blocked up to pool_timeout (30s) and the
# backend returned nothing (HTTP 000). Size the pool to the threadpool so it
# doesn't starve under load.
#   pool_pre_ping — drop connections the DB already closed (e.g. after a restart)
#   pool_recycle  — retire connections before Postgres' idle timeout kills them
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "30"))

engine = create_engine(
    DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=30,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
