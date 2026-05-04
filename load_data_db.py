"""Utilities for loading and clearing sample Map-Service data."""

from __future__ import annotations

from contextlib import nullcontext
from typing import Optional

from database import SessionLocal, init_db
from models import Closure, Edge, EmergencyRoute, Node, Tile


def _session_scope(session=None):
    if session is not None:
        return nullcontext(session)
    return SessionLocal()


def clear_all_data(session=None) -> None:
    """Remove all graph and map data from the database."""
    if session is None:
        init_db()
    with _session_scope(session) as db:
        db.query(Closure).delete(synchronize_session=False)
        db.query(EmergencyRoute).delete(synchronize_session=False)
        db.query(Edge).delete(synchronize_session=False)
        db.query(Tile).delete(synchronize_session=False)
        db.query(Node).delete(synchronize_session=False)
        db.commit()


def load_sample_data(session=None) -> None:
    """Load a small sample stadium graph used by the reset endpoint."""
    if session is None:
        init_db()
    with _session_scope(session) as db:
        nodes = [
            Node(id="SAMPLE-CORRIDOR-1", name="Main Corridor", type="corridor", x=100.0, y=100.0, level=0),
            Node(id="SAMPLE-GATE-1", name="Gate 1", type="gate", x=150.0, y=100.0, level=0, num_servers=2, service_rate=6.0),
            Node(id="SAMPLE-BAR-1", name="Bar 1", type="bar", x=200.0, y=100.0, level=0, num_servers=1, service_rate=4.0),
            Node(id="SAMPLE-EXIT-1", name="Exit 1", type="emergency_exit", x=250.0, y=100.0, level=0),
        ]
        edges = [
            Edge(id="SAMPLE-E-1", from_id="SAMPLE-CORRIDOR-1", to_id="SAMPLE-GATE-1", weight=5.0, accessible=True),
            Edge(id="SAMPLE-E-2", from_id="SAMPLE-GATE-1", to_id="SAMPLE-BAR-1", weight=4.0, accessible=True),
            Edge(id="SAMPLE-E-3", from_id="SAMPLE-BAR-1", to_id="SAMPLE-EXIT-1", weight=3.0, accessible=True),
        ]

        db.add_all(nodes + edges)
        db.commit()