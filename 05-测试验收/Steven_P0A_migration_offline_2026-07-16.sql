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

COMMIT;

