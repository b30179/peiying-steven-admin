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

COMMIT;

