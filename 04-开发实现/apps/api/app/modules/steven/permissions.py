from __future__ import annotations

from app.core.auth import require_permissions
from app.core.permissions import AUDIT_READ_ALL, DASHBOARD_READ

require_steven = require_permissions(DASHBOARD_READ)
require_audit_reader = require_permissions(AUDIT_READ_ALL)
