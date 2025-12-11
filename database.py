from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from config import Config
from models import Base

engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db(): # criar as tabelas
    Base.metadata.create_all(bind=engine)

def get_db() -> Session: # usar assim: def endpoint(db: Session = Depends(get_db))
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()