import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Isolated test config, set before any `app.*` module is imported so the
# lru_cache'd settings singleton and the DB engine pick these up.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ai_cost_governor.db")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-for-pytest-only")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-pytest-only")
