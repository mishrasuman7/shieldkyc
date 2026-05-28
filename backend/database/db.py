# database/db.py — sets up the connection to our SQLite database
# and gives the rest of the app a clean way to talk to it.

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# The database is a single file, shieldkyc.db, created in the backend/ folder.
# "sqlite:///./shieldkyc.db" means: SQLite, file path relative to where we run.
DATABASE_URL = "sqlite:///./shieldkyc.db"

# The engine is the core connection to the database.
# check_same_thread=False is SQLite-specific: by default SQLite refuses to be
# used across different threads, but FastAPI may handle requests on different
# threads. This flag allows it. It's safe because we open a fresh session per
# request (see get_db below) rather than sharing one connection everywhere.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# A "session" is one conversation with the database (a unit of work).
# SessionLocal is a factory — call it to get a new session.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class all our table models inherit from.
# SQLAlchemy uses it to keep a registry of every table we define.
Base = declarative_base()

# get_db is a FastAPI "dependency". Any endpoint that needs the database
# declares it, and FastAPI automatically opens a session before the request
# and closes it after — even if an error occurs. This prevents leaked
# connections, a common source of mysterious slowdowns.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()