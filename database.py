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
    from sqlalchemy import inspect, text
    
    # Create all tables first
    Base.metadata.create_all(bind=engine)
    
    # Ensure all columns exist (for schema migrations)
    inspector = inspect(engine)
    if 'nodes' in inspector.get_table_names():
        existing_columns = [col['name'] for col in inspector.get_columns('nodes')]
        required_columns = {col.name: col for col in Base.metadata.tables['nodes'].columns}
        
        with engine.begin() as conn:
            for col_name, col_obj in required_columns.items():
                if col_name not in existing_columns:
                    # Add missing column
                    col_type = str(col_obj.type.compile(dialect=engine.dialect))
                    nullable = "NULL" if col_obj.nullable else "NOT NULL"
                    sql = text(f"ALTER TABLE nodes ADD COLUMN {col_name} {col_type} {nullable}")
                    conn.execute(sql)

def get_db() -> Session: # usar assim: def endpoint(db: Session = Depends(get_db))
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()