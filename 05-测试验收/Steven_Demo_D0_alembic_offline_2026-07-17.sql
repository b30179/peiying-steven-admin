BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 20260716_0001

CREATE TABLE steven_quote_jobs (
    id VARCHAR(36) NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    status VARCHAR(32) DEFAULT 'draft' NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE steven_quote_items (
    id VARCHAR(36) NOT NULL, 
    quote_job_id VARCHAR(36) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    quantity NUMERIC(14, 2) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_steven_quote_items_quantity_positive CHECK (quantity > 0), 
    FOREIGN KEY(quote_job_id) REFERENCES steven_quote_jobs (id) ON DELETE CASCADE
);

CREATE TABLE steven_quote_suppliers (
    id VARCHAR(36) NOT NULL, 
    quote_job_id VARCHAR(36) NOT NULL, 
    supplier_name VARCHAR(200) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    freight NUMERIC(14, 2) DEFAULT '0' NOT NULL, 
    tax NUMERIC(14, 2) DEFAULT '0' NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_steven_quote_suppliers_freight_nonnegative CHECK (freight >= 0), 
    CONSTRAINT ck_steven_quote_suppliers_tax_nonnegative CHECK (tax >= 0), 
    FOREIGN KEY(quote_job_id) REFERENCES steven_quote_jobs (id) ON DELETE CASCADE
);

CREATE TABLE steven_quote_offer_lines (
    id VARCHAR(36) NOT NULL, 
    quote_supplier_id VARCHAR(36) NOT NULL, 
    quote_item_id VARCHAR(36) NOT NULL, 
    unit_price NUMERIC(14, 2) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_steven_quote_offer_lines_unit_price_nonnegative CHECK (unit_price >= 0), 
    CONSTRAINT uq_steven_quote_offer_lines_supplier_item UNIQUE (quote_supplier_id, quote_item_id), 
    FOREIGN KEY(quote_supplier_id) REFERENCES steven_quote_suppliers (id) ON DELETE CASCADE, 
    FOREIGN KEY(quote_item_id) REFERENCES steven_quote_items (id) ON DELETE CASCADE
);

INSERT INTO alembic_version (version_num) VALUES ('20260716_0001') RETURNING alembic_version.version_num;

-- Running upgrade 20260716_0001 -> 20260716_0002

ALTER TABLE steven_quote_jobs RENAME title TO subject;

ALTER TABLE steven_quote_jobs ADD COLUMN recommended_supplier_id VARCHAR(36);

ALTER TABLE steven_quote_jobs ADD COLUMN non_lowest_reason TEXT;

ALTER TABLE steven_quote_jobs ADD COLUMN approval_opinion TEXT;

ALTER TABLE steven_quote_jobs ADD COLUMN source_file_id VARCHAR(36);

ALTER TABLE steven_quote_jobs ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_jobs ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_jobs ADD COLUMN created_by VARCHAR(100) DEFAULT 'migration' NOT NULL;

ALTER TABLE steven_quote_jobs ADD COLUMN updated_by VARCHAR(100) DEFAULT 'migration' NOT NULL;

ALTER TABLE steven_quote_items RENAME name TO item;

ALTER TABLE steven_quote_items RENAME quantity TO qty;

ALTER TABLE steven_quote_items DROP CONSTRAINT ck_steven_quote_items_quantity_positive;

ALTER TABLE steven_quote_items ADD CONSTRAINT ck_steven_quote_items_qty_positive CHECK (qty > 0);

ALTER TABLE steven_quote_items ADD COLUMN item_code VARCHAR(50);

UPDATE steven_quote_items SET item_code = id WHERE item_code IS NULL;

ALTER TABLE steven_quote_items ALTER COLUMN item_code SET NOT NULL;

ALTER TABLE steven_quote_items ADD COLUMN specification VARCHAR(500) DEFAULT '' NOT NULL;

ALTER TABLE steven_quote_items ADD COLUMN unit VARCHAR(30) DEFAULT '件' NOT NULL;

ALTER TABLE steven_quote_items ADD COLUMN status VARCHAR(32) DEFAULT 'draft' NOT NULL;

ALTER TABLE steven_quote_items ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_items ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_items ADD COLUMN created_by VARCHAR(100) DEFAULT 'migration' NOT NULL;

ALTER TABLE steven_quote_items ADD COLUMN updated_by VARCHAR(100) DEFAULT 'migration' NOT NULL;

ALTER TABLE steven_quote_items ADD CONSTRAINT uq_steven_quote_items_job_code UNIQUE (quote_job_id, item_code);

ALTER TABLE steven_quote_suppliers ADD COLUMN supplier_code VARCHAR(50);

UPDATE steven_quote_suppliers SET supplier_code = id WHERE supplier_code IS NULL;

ALTER TABLE steven_quote_suppliers ALTER COLUMN supplier_code SET NOT NULL;

ALTER TABLE steven_quote_suppliers ADD COLUMN valid_until DATE DEFAULT '2099-12-31'::date NOT NULL;

ALTER TABLE steven_quote_suppliers ADD COLUMN subtotal NUMERIC(14, 2) DEFAULT '0' NOT NULL;

ALTER TABLE steven_quote_suppliers ADD COLUMN total NUMERIC(14, 2) DEFAULT '0' NOT NULL;

ALTER TABLE steven_quote_suppliers ADD COLUMN source_file_id VARCHAR(36);

ALTER TABLE steven_quote_suppliers ADD COLUMN status VARCHAR(32) DEFAULT 'draft' NOT NULL;

ALTER TABLE steven_quote_suppliers ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_suppliers ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_suppliers ADD COLUMN created_by VARCHAR(100) DEFAULT 'migration' NOT NULL;

ALTER TABLE steven_quote_suppliers ADD COLUMN updated_by VARCHAR(100) DEFAULT 'migration' NOT NULL;

ALTER TABLE steven_quote_suppliers ADD CONSTRAINT ck_steven_quote_suppliers_subtotal_nonnegative CHECK (subtotal >= 0);

ALTER TABLE steven_quote_suppliers ADD CONSTRAINT ck_steven_quote_suppliers_total_nonnegative CHECK (total >= 0);

ALTER TABLE steven_quote_suppliers ADD CONSTRAINT uq_steven_quote_suppliers_job_code UNIQUE (quote_job_id, supplier_code);

ALTER TABLE steven_quote_suppliers ADD CONSTRAINT uq_steven_quote_suppliers_job_name UNIQUE (quote_job_id, supplier_name);

ALTER TABLE steven_quote_offer_lines ADD COLUMN line_total NUMERIC(14, 2) DEFAULT '0' NOT NULL;

ALTER TABLE steven_quote_offer_lines ADD COLUMN remark TEXT DEFAULT '' NOT NULL;

ALTER TABLE steven_quote_offer_lines ADD COLUMN status VARCHAR(32) DEFAULT 'draft' NOT NULL;

ALTER TABLE steven_quote_offer_lines ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_offer_lines ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_offer_lines ADD COLUMN created_by VARCHAR(100) DEFAULT 'migration' NOT NULL;

ALTER TABLE steven_quote_offer_lines ADD COLUMN updated_by VARCHAR(100) DEFAULT 'migration' NOT NULL;

ALTER TABLE steven_quote_offer_lines ADD CONSTRAINT ck_steven_quote_offer_lines_total_nonnegative CHECK (line_total >= 0);

ALTER TABLE steven_quote_jobs ADD CONSTRAINT fk_steven_quote_jobs_recommended_supplier FOREIGN KEY(recommended_supplier_id) REFERENCES steven_quote_suppliers (id) ON DELETE SET NULL;

CREATE TABLE steven_quote_import_batches (
    id VARCHAR(36) NOT NULL, 
    quote_job_id VARCHAR(36) NOT NULL, 
    filename VARCHAR(255) NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    status VARCHAR(32) DEFAULT 'prechecked' NOT NULL, 
    issue_count INTEGER DEFAULT '0' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by VARCHAR(100) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(quote_job_id) REFERENCES steven_quote_jobs (id) ON DELETE CASCADE
);

CREATE TABLE steven_quote_approvals (
    id VARCHAR(36) NOT NULL, 
    quote_job_id VARCHAR(36) NOT NULL, 
    submitted_by VARCHAR(100) NOT NULL, 
    status VARCHAR(32) DEFAULT 'pending' NOT NULL, 
    opinion TEXT, 
    decided_by VARCHAR(100), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(quote_job_id) REFERENCES steven_quote_jobs (id) ON DELETE CASCADE
);

CREATE TABLE steven_quote_versions (
    id VARCHAR(36) NOT NULL, 
    quote_job_id VARCHAR(36) NOT NULL, 
    version_number INTEGER NOT NULL, 
    filename VARCHAR(255) NOT NULL, 
    storage_key VARCHAR(500) NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_by VARCHAR(100) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_steven_quote_versions_positive CHECK (version_number > 0), 
    CONSTRAINT uq_steven_quote_versions_job_version UNIQUE (quote_job_id, version_number), 
    FOREIGN KEY(quote_job_id) REFERENCES steven_quote_jobs (id) ON DELETE CASCADE
);

CREATE INDEX ix_steven_quote_suppliers_valid_until ON steven_quote_suppliers (valid_until);

CREATE INDEX ix_steven_quote_jobs_status ON steven_quote_jobs (status);

UPDATE alembic_version SET version_num='20260716_0002' WHERE alembic_version.version_num = '20260716_0001';

-- Running upgrade 20260716_0002 -> 20260716_0003

CREATE TABLE users (
    id VARCHAR(36) NOT NULL, 
    username VARCHAR(100) NOT NULL, 
    display_name VARCHAR(200) NOT NULL, 
    email VARCHAR(320), 
    password_hash TEXT NOT NULL, 
    status VARCHAR(32) DEFAULT 'active' NOT NULL, 
    failed_login_count INTEGER DEFAULT '0' NOT NULL, 
    locked_until TIMESTAMP WITH TIME ZONE, 
    last_login_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_users_status CHECK (status IN ('active','disabled','locked')), 
    CONSTRAINT uq_users_username UNIQUE (username), 
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE INDEX ix_users_status ON users (status);

CREATE TABLE roles (
    id VARCHAR(36) NOT NULL, 
    code VARCHAR(100) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    status VARCHAR(32) DEFAULT 'active' NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_roles_status CHECK (status IN ('active','disabled')), 
    CONSTRAINT uq_roles_code UNIQUE (code)
);

CREATE TABLE permissions (
    id VARCHAR(36) NOT NULL, 
    code VARCHAR(150) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    module VARCHAR(100) NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_permissions_code UNIQUE (code)
);

CREATE INDEX ix_permissions_module ON permissions (module);

CREATE TABLE user_roles (
    user_id VARCHAR(36) NOT NULL, 
    role_id VARCHAR(36) NOT NULL, 
    assigned_by VARCHAR(36), 
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_user_roles PRIMARY KEY (user_id, role_id), 
    CONSTRAINT uq_user_roles_user_role UNIQUE (user_id, role_id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
    FOREIGN KEY(assigned_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_user_roles_role_id ON user_roles (role_id);

CREATE TABLE role_permissions (
    role_id VARCHAR(36) NOT NULL, 
    permission_id VARCHAR(36) NOT NULL, 
    CONSTRAINT pk_role_permissions PRIMARY KEY (role_id, permission_id), 
    CONSTRAINT uq_role_permissions_role_permission UNIQUE (role_id, permission_id), 
    FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
    FOREIGN KEY(permission_id) REFERENCES permissions (id) ON DELETE CASCADE
);

CREATE INDEX ix_role_permissions_permission_id ON role_permissions (permission_id);

CREATE TABLE auth_sessions (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    idle_expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    absolute_expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    revoke_reason VARCHAR(200), 
    ip_hash VARCHAR(64), 
    user_agent_hash VARCHAR(64), 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_auth_sessions_absolute_expiry CHECK (absolute_expires_at > created_at), 
    CONSTRAINT ck_auth_sessions_idle_expiry CHECK (idle_expires_at <= absolute_expires_at), 
    CONSTRAINT uq_auth_sessions_token_hash UNIQUE (token_hash), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_auth_sessions_user_active ON auth_sessions (user_id, is_active);

CREATE INDEX ix_auth_sessions_expiry ON auth_sessions (idle_expires_at, absolute_expires_at);

INSERT INTO roles (id, code, name, status) VALUES ('role-steven', 'steven', 'Steven', 'active');

INSERT INTO roles (id, code, name, status) VALUES ('role-approver', 'approver', '审批人', 'active');

INSERT INTO roles (id, code, name, status) VALUES ('role-admin', 'admin', '管理员', 'active');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-dashboard-read', 'steven:dashboard:read', '读取 Steven Dashboard', 'steven');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-quotes-read', 'steven:quotes:read', '读取采购比价', 'steven');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-quotes-write', 'steven:quotes:write', '写入采购比价', 'steven');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-quotes-import', 'steven:quotes:import', '导入采购比价', 'steven');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-quotes-recommend', 'steven:quotes:recommend', '填写人工推荐', 'steven');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-quotes-submit', 'steven:quotes:submit', '提交采购审批', 'steven');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-quotes-approve', 'steven:quotes:approve', '批准或退回采购审批', 'steven');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-quotes-export', 'steven:quotes:export', '导出已批准采购比价', 'steven');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-quotes-audit-scoped', 'steven:quotes:audit:read_scoped', '读取事项级审计', 'steven');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-audit-read-all', 'audit:logs:read_all', '读取平台全量审计', 'platform');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-accounts-manage', 'accounts:manage', '管理账户', 'platform');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-roles-manage', 'roles:manage', '管理角色', 'platform');

INSERT INTO permissions (id, code, name, module) VALUES ('perm-sessions-manage', 'sessions:manage', '管理会话', 'platform');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-steven', 'perm-dashboard-read');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-steven', 'perm-quotes-read');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-steven', 'perm-quotes-write');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-steven', 'perm-quotes-import');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-steven', 'perm-quotes-recommend');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-steven', 'perm-quotes-submit');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-steven', 'perm-quotes-export');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-steven', 'perm-quotes-audit-scoped');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-approver', 'perm-quotes-read');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-approver', 'perm-quotes-approve');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-approver', 'perm-quotes-audit-scoped');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-admin', 'perm-audit-read-all');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-admin', 'perm-accounts-manage');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-admin', 'perm-roles-manage');

INSERT INTO role_permissions (role_id, permission_id) VALUES ('role-admin', 'perm-sessions-manage');

UPDATE alembic_version SET version_num='20260716_0003' WHERE alembic_version.version_num = '20260716_0002';

-- Running upgrade 20260716_0003 -> 20260716_0004

CREATE TABLE auth_security_events (
    id VARCHAR(36) NOT NULL, 
    event_type VARCHAR(100) NOT NULL, 
    outcome VARCHAR(32) NOT NULL, 
    actor_user_id VARCHAR(36), 
    subject_user_id VARCHAR(36), 
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    details JSONB DEFAULT '{}'::jsonb NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_auth_security_events_outcome CHECK (outcome IN ('success','rejected','failed')), 
    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(subject_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_auth_security_events_type_time ON auth_security_events (event_type, occurred_at);

CREATE INDEX ix_auth_security_events_subject_time ON auth_security_events (subject_user_id, occurred_at);

UPDATE alembic_version SET version_num='20260716_0004' WHERE alembic_version.version_num = '20260716_0003';

-- Running upgrade 20260716_0004 -> 20260716_0005

ALTER TABLE steven_quote_jobs ADD COLUMN is_demo BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE steven_quote_jobs ADD COLUMN demo_label TEXT;

ALTER TABLE steven_quote_jobs ADD COLUMN approval_id VARCHAR(36);

ALTER TABLE steven_quote_jobs ADD COLUMN next_export_version INTEGER DEFAULT '1' NOT NULL;

ALTER TABLE steven_quote_jobs ADD CONSTRAINT ck_steven_quote_jobs_status CHECK (status IN ('draft','incomplete','ready_for_review','pending_approval','approved','exported'));

ALTER TABLE steven_quote_jobs ADD CONSTRAINT ck_steven_quote_jobs_next_export_version CHECK (next_export_version > 0);

ALTER TABLE steven_quote_jobs ADD CONSTRAINT fk_steven_quote_jobs_approval FOREIGN KEY(approval_id) REFERENCES steven_quote_approvals (id) ON DELETE SET NULL;

ALTER TABLE steven_quote_import_batches ADD COLUMN valid BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE steven_quote_import_batches ADD COLUMN payload_sha256 VARCHAR(64) DEFAULT '0000000000000000000000000000000000000000000000000000000000000000' NOT NULL;

ALTER TABLE steven_quote_import_batches ALTER COLUMN payload_sha256 DROP DEFAULT;

ALTER TABLE steven_quote_import_batches ADD COLUMN issues JSONB DEFAULT '[]'::jsonb NOT NULL;

ALTER TABLE steven_quote_import_batches ADD COLUMN payload JSONB DEFAULT '{}'::jsonb NOT NULL;

ALTER TABLE steven_quote_import_batches ADD COLUMN confirmed_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE steven_quote_import_batches ADD COLUMN confirmed_by VARCHAR(36);

ALTER TABLE steven_quote_import_batches ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_import_batches ADD COLUMN updated_by VARCHAR(36) DEFAULT 'migration' NOT NULL;

ALTER TABLE steven_quote_import_batches ADD CONSTRAINT ck_steven_quote_import_batches_status CHECK (status IN ('prechecked','confirmed','rejected'));

ALTER TABLE steven_quote_import_batches ADD CONSTRAINT fk_steven_quote_import_batches_confirmed_by FOREIGN KEY(confirmed_by) REFERENCES users (id) ON DELETE SET NULL;

CREATE INDEX ix_steven_quote_import_batches_job_status ON steven_quote_import_batches (quote_job_id, status);

ALTER TABLE steven_quote_approvals ADD COLUMN submitted_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_approvals ADD COLUMN decided_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE steven_quote_approvals ADD CONSTRAINT ck_steven_quote_approvals_status CHECK (status IN ('pending','approved','rejected'));

ALTER TABLE steven_quote_approvals ADD CONSTRAINT fk_steven_quote_approvals_submitted_by FOREIGN KEY (submitted_by) REFERENCES users(id) ON DELETE RESTRICT NOT VALID;

ALTER TABLE steven_quote_approvals ADD CONSTRAINT fk_steven_quote_approvals_decided_by FOREIGN KEY (decided_by) REFERENCES users(id) ON DELETE RESTRICT NOT VALID;

CREATE UNIQUE INDEX uq_steven_quote_approvals_one_pending ON steven_quote_approvals (quote_job_id) WHERE status = 'pending';

CREATE INDEX ix_steven_quote_approvals_status_time ON steven_quote_approvals (status, submitted_at);

ALTER TABLE steven_quote_versions ALTER COLUMN sha256 DROP NOT NULL;

ALTER TABLE steven_quote_versions ADD COLUMN object_type VARCHAR(50) DEFAULT 'steven_quote_job' NOT NULL;

ALTER TABLE steven_quote_versions ADD COLUMN object_id VARCHAR(36);

UPDATE steven_quote_versions SET object_id = quote_job_id WHERE object_id IS NULL;

ALTER TABLE steven_quote_versions ALTER COLUMN object_id SET NOT NULL;

ALTER TABLE steven_quote_versions ADD COLUMN status VARCHAR(32) DEFAULT 'ready' NOT NULL;

ALTER TABLE steven_quote_versions ADD COLUMN mime_type VARCHAR(150) DEFAULT 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' NOT NULL;

ALTER TABLE steven_quote_versions ADD COLUMN size_bytes BIGINT;

ALTER TABLE steven_quote_versions ADD COLUMN failure_reason TEXT;

ALTER TABLE steven_quote_versions ADD COLUMN temporary_storage_key VARCHAR(500);

ALTER TABLE steven_quote_versions ADD COLUMN published_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE steven_quote_versions ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL;

ALTER TABLE steven_quote_versions ADD CONSTRAINT ck_steven_quote_versions_status CHECK (status IN ('reserved','ready','failed'));

ALTER TABLE steven_quote_versions ADD CONSTRAINT ck_steven_quote_versions_size CHECK (size_bytes IS NULL OR size_bytes >= 0);

ALTER TABLE steven_quote_versions ADD CONSTRAINT uq_steven_quote_versions_storage_key UNIQUE (storage_key);

CREATE INDEX ix_steven_quote_versions_status_time ON steven_quote_versions (status, created_at);

CREATE TABLE steven_quote_audit_events (
    id VARCHAR(36) NOT NULL, 
    actor_user_id VARCHAR(36) NOT NULL, 
    action VARCHAR(100) NOT NULL, 
    object_type VARCHAR(100) NOT NULL, 
    object_id VARCHAR(36) NOT NULL, 
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    request_id VARCHAR(100), 
    before_after JSONB DEFAULT '{}'::jsonb NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_steven_quote_audit_object_time ON steven_quote_audit_events (object_id, occurred_at);

CREATE INDEX ix_steven_quote_audit_actor_time ON steven_quote_audit_events (actor_user_id, occurred_at);

UPDATE alembic_version SET version_num='20260716_0005' WHERE alembic_version.version_num = '20260716_0004';

-- Running upgrade 20260716_0005 -> 20260716_0006

DO $$
        DECLARE conflict_report text;
        BEGIN
            SELECT string_agg(normalized_username || ' => [' || usernames || ']', '; ' ORDER BY normalized_username)
              INTO conflict_report
              FROM (
                    SELECT lower(username) AS normalized_username,
                           string_agg(username, ', ' ORDER BY username) AS usernames
                      FROM users
                     GROUP BY lower(username)
                    HAVING count(*) > 1
              ) conflicts;
            IF conflict_report IS NOT NULL THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23505',
                    MESSAGE = 'case-insensitive username conflicts must be governed before migration: ' || conflict_report;
            END IF;
        END $$;;

CREATE UNIQUE INDEX uq_users_username_lower ON users (lower(username));

CREATE TABLE platform_audit_events (
    id VARCHAR(36) NOT NULL, 
    actor_user_id VARCHAR(36), 
    actor_label VARCHAR(200), 
    action VARCHAR(150) NOT NULL, 
    outcome VARCHAR(32) NOT NULL, 
    object_type VARCHAR(100) NOT NULL, 
    object_id VARCHAR(100) NOT NULL, 
    request_id VARCHAR(100), 
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    before_after JSONB DEFAULT '{}'::jsonb NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_platform_audit_events_outcome CHECK (outcome IN ('success','rejected','failed')), 
    FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_platform_audit_request_time ON platform_audit_events (request_id, occurred_at);

CREATE INDEX ix_platform_audit_object_time ON platform_audit_events (object_type, object_id, occurred_at);

CREATE INDEX ix_platform_audit_actor_time ON platform_audit_events (actor_user_id, occurred_at);

CREATE INDEX ix_platform_audit_action_time ON platform_audit_events (action, occurred_at);

UPDATE alembic_version SET version_num='20260716_0006' WHERE alembic_version.version_num = '20260716_0005';

-- Running upgrade 20260716_0006 -> 20260717_0007

CREATE TABLE files (
    id VARCHAR(36) NOT NULL, 
    module VARCHAR(50) NOT NULL, 
    document_type VARCHAR(100) NOT NULL, 
    purpose VARCHAR(100) NOT NULL, 
    original_filename VARCHAR(255) NOT NULL, 
    storage_key VARCHAR(500) NOT NULL, 
    mime_type VARCHAR(150) NOT NULL, 
    size_bytes BIGINT NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    is_demo BOOLEAN DEFAULT false NOT NULL, 
    created_by VARCHAR(36) NOT NULL, 
    request_id VARCHAR(100) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_files_size CHECK (size_bytes >= 0), 
    CONSTRAINT ck_files_status CHECK (status IN ('stored','failed')), 
    CONSTRAINT uq_files_storage_key UNIQUE (storage_key), 
    FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_files_sha256 ON files (sha256);

CREATE INDEX ix_files_request ON files (request_id);

CREATE INDEX ix_files_route_time ON files (module, document_type, purpose, created_at);

CREATE TABLE ocr_jobs (
    id VARCHAR(36) NOT NULL, 
    file_id VARCHAR(36) NOT NULL, 
    module VARCHAR(50) NOT NULL, 
    document_type VARCHAR(100) NOT NULL, 
    purpose VARCHAR(100) NOT NULL, 
    provider VARCHAR(100) NOT NULL, 
    model VARCHAR(150) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    request_id VARCHAR(100) NOT NULL, 
    output_json JSONB DEFAULT '{}'::jsonb NOT NULL, 
    error_code VARCHAR(100), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_ocr_jobs_status CHECK (status IN ('pending','running','needs_review','confirmed','rejected','failed')), 
    FOREIGN KEY(file_id) REFERENCES files (id) ON DELETE RESTRICT
);

CREATE INDEX ix_ocr_jobs_file_time ON ocr_jobs (file_id, created_at);

CREATE INDEX ix_ocr_jobs_request ON ocr_jobs (request_id);

CREATE INDEX ix_ocr_jobs_route_status ON ocr_jobs (module, document_type, purpose, status);

CREATE TABLE ai_jobs (
    id VARCHAR(36) NOT NULL, 
    file_id VARCHAR(36) NOT NULL, 
    module VARCHAR(50) NOT NULL, 
    document_type VARCHAR(100) NOT NULL, 
    purpose VARCHAR(100) NOT NULL, 
    provider VARCHAR(100) NOT NULL, 
    model VARCHAR(150) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    request_id VARCHAR(100) NOT NULL, 
    output_json JSONB DEFAULT '{}'::jsonb NOT NULL, 
    error_code VARCHAR(100), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_ai_jobs_status CHECK (status IN ('pending','running','needs_review','confirmed','rejected','failed')), 
    FOREIGN KEY(file_id) REFERENCES files (id) ON DELETE RESTRICT
);

CREATE INDEX ix_ai_jobs_file_time ON ai_jobs (file_id, created_at);

CREATE INDEX ix_ai_jobs_request ON ai_jobs (request_id);

CREATE INDEX ix_ai_jobs_route_status ON ai_jobs (module, document_type, purpose, status);

CREATE TABLE review_candidates (
    id VARCHAR(36) NOT NULL, 
    source_file_id VARCHAR(36) NOT NULL, 
    ocr_job_id VARCHAR(36), 
    ai_job_id VARCHAR(36), 
    module VARCHAR(50) NOT NULL, 
    document_type VARCHAR(100) NOT NULL, 
    purpose VARCHAR(100) NOT NULL, 
    schema_name VARCHAR(150) NOT NULL, 
    schema_version VARCHAR(30) NOT NULL, 
    provider VARCHAR(200) NOT NULL, 
    model VARCHAR(300) NOT NULL, 
    status VARCHAR(32) NOT NULL, 
    candidate_json JSONB DEFAULT '{}'::jsonb NOT NULL, 
    human_revision_json JSONB, 
    warnings JSONB DEFAULT '[]'::jsonb NOT NULL, 
    evidence JSONB DEFAULT '[]'::jsonb NOT NULL, 
    reviewer_id VARCHAR(36), 
    target_object_type VARCHAR(100), 
    target_object_id VARCHAR(36), 
    request_id VARCHAR(100) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    reviewed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_review_candidates_status CHECK (status IN ('pending','running','needs_review','confirmed','rejected','failed')), 
    FOREIGN KEY(source_file_id) REFERENCES files (id) ON DELETE RESTRICT, 
    FOREIGN KEY(ocr_job_id) REFERENCES ocr_jobs (id) ON DELETE SET NULL, 
    FOREIGN KEY(ai_job_id) REFERENCES ai_jobs (id) ON DELETE SET NULL, 
    FOREIGN KEY(reviewer_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_review_candidates_request ON review_candidates (request_id);

CREATE INDEX ix_review_candidates_route_status ON review_candidates (module, document_type, purpose, status);

CREATE INDEX ix_review_candidates_target_time ON review_candidates (target_object_type, target_object_id, created_at);

CREATE TABLE steven_quote_import_candidates (
    candidate_id VARCHAR(36) NOT NULL, 
    quote_job_id VARCHAR(36) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (candidate_id), 
    FOREIGN KEY(candidate_id) REFERENCES review_candidates (id) ON DELETE RESTRICT, 
    FOREIGN KEY(quote_job_id) REFERENCES steven_quote_jobs (id) ON DELETE RESTRICT
);

CREATE INDEX ix_steven_quote_import_candidates_job ON steven_quote_import_candidates (quote_job_id, created_at);

UPDATE alembic_version SET version_num='20260717_0007' WHERE alembic_version.version_num = '20260716_0006';

COMMIT;
