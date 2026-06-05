from contextlib import contextmanager
from functools import wraps

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.load_env import load_env_file
from config.settings import get_database_url


load_env_file()
DATABASE_URL = get_database_url()

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


@contextmanager
def _transaction_context():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def db_transaction(function=None):
    if function is None:
        return _transaction_context()

    @wraps(function)
    def wrapper(*args, **kwargs):
        with _transaction_context() as db:
            return function(*args, db=db, **kwargs)

    return wrapper
