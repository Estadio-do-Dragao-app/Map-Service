from sqlalchemy.orm import Session
from models import Node, Edge, Closure, Tile, EmergencyRoute, Camera

def clear_all_data(db: Session) -> None:
    db.query(Closure).delete()
    db.query(EmergencyRoute).delete()
    db.query(Edge).delete()
    db.query(Tile).delete()
    db.query(Camera).delete()
    db.query(Node).delete()
    db.commit()

def load_sample_data(db: Session) -> None:
    pass