from __future__ import annotations

from app.core.auth import require_permissions
from app.core.permissions import (
    TENDERS_APPROVE,
    TENDERS_AUDIT_SCOPED,
    TENDERS_EXPORT,
    TENDERS_READ,
    TENDERS_PROOFREAD,
    TENDERS_SUBMIT,
    TENDERS_WRITE,
)

require_tender_reader = require_permissions(TENDERS_READ)
require_tender_writer = require_permissions(TENDERS_WRITE)
require_tender_submitter = require_permissions(TENDERS_SUBMIT)
require_tender_approver = require_permissions(TENDERS_APPROVE)
require_tender_exporter = require_permissions(TENDERS_EXPORT)
require_tender_audit_reader = require_permissions(TENDERS_AUDIT_SCOPED)

require_tender_proofreader = require_permissions(TENDERS_PROOFREAD)
