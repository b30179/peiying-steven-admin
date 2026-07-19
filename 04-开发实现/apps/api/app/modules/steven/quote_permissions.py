from __future__ import annotations

from app.core.auth import require_permissions
from app.core.permissions import (
    QUOTES_APPROVE,
    QUOTES_AUDIT_SCOPED,
    QUOTES_EXPORT,
    QUOTES_IMPORT,
    QUOTES_READ,
    QUOTES_RECOMMEND,
    QUOTES_SUBMIT,
    QUOTES_WRITE,
)

require_quote_reader = require_permissions(QUOTES_READ)
require_quote_writer = require_permissions(QUOTES_WRITE)
require_quote_importer = require_permissions(QUOTES_IMPORT)
require_quote_recommender = require_permissions(QUOTES_RECOMMEND)
require_quote_submitter = require_permissions(QUOTES_SUBMIT)
require_quote_approver = require_permissions(QUOTES_APPROVE)
require_quote_exporter = require_permissions(QUOTES_EXPORT)
require_quote_audit_reader = require_permissions(QUOTES_AUDIT_SCOPED)
