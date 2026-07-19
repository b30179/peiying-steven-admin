from __future__ import annotations

from app.core.auth import require_permissions
from app.core.permissions import (
    INVENTORY_APPROVE,
    INVENTORY_AUDIT_SCOPED,
    INVENTORY_COUNT,
    INVENTORY_EXPORT,
    INVENTORY_READ,
    INVENTORY_SUBMIT,
    INVENTORY_WRITE,
)

require_inventory_reader = require_permissions(INVENTORY_READ)
require_inventory_writer = require_permissions(INVENTORY_WRITE)
require_inventory_counter = require_permissions(INVENTORY_COUNT)
require_inventory_submitter = require_permissions(INVENTORY_SUBMIT)
require_inventory_approver = require_permissions(INVENTORY_APPROVE)
require_inventory_exporter = require_permissions(INVENTORY_EXPORT)
require_inventory_audit_reader = require_permissions(INVENTORY_AUDIT_SCOPED)
