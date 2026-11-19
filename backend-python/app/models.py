"""Imports every module's tables so Alembic sees the full metadata."""
from app.db import Base  # noqa: F401
from app.modules.debate.models import Comment  # noqa: F401
from app.modules.forecasts.models import Question, Topic, Vote  # noqa: F401
from app.modules.identity.models import User  # noqa: F401
from app.modules.news.models import NewsItem  # noqa: F401
