"""Read/write SystemSetting with a tiny in-process cache."""
from app.extensions import db
from app.models.settings import SystemSetting

_cache = {}


def get_setting(key, default=None):
    if key in _cache:
        return _cache[key]
    row = SystemSetting.query.filter_by(key=key).first()
    value = row.value if row and row.value is not None else default
    _cache[key] = value
    return value


def set_setting(key, value):
    row = SystemSetting.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemSetting(key=key, value=value))
    else:
        row.value = value
    _cache[key] = value
    db.session.commit()