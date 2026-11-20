"""Imports every module's tables so Alembic sees the full metadata."""
from app.db import Base  # noqa: F401
from app.modules.compliance.models import Grievance, GrievanceNote, QuietPeriod  # noqa: F401
from app.modules.debate.models import Comment, CommentReport, ModerationAction, UserBlock  # noqa: F401
from app.modules.engagement.models import CheckIn, Quiz, QuizAnswer  # noqa: F401
from app.modules.forecasts.models import Call, Dispute, Question, Settlement, Topic  # noqa: F401
from app.modules.governance.models import AdminAudit, AdminSession, AdminUser, ErrorDay  # noqa: F401
from app.modules.identity.models import ActivityDay, AppSession, User  # noqa: F401
from app.modules.ledger.models import LedgerBalance, LedgerEntry, LedgerTransaction  # noqa: F401
from app.modules.news.models import NewsItem  # noqa: F401
from app.modules.policy.service import Policy  # noqa: F401
from app.modules.standing.models import Badge  # noqa: F401
from app.ratelimit import RateLimitCounter  # noqa: F401
