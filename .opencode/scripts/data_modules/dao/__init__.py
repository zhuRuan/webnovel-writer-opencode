from pathlib import Path
from .base import BaseDAO

_instances = {}

def get_dao(dao_class, db_path: str | Path):
    key = (dao_class.__name__, str(db_path))
    if key not in _instances:
        _instances[key] = dao_class(db_path)
    return _instances[key]
