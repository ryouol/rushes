CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE "user" (
	name VARCHAR(120) NOT NULL,
	id UUID NOT NULL,
	email VARCHAR(320) NOT NULL,
	hashed_password VARCHAR(1024) NOT NULL,
	is_active BOOLEAN NOT NULL,
	is_superuser BOOLEAN NOT NULL,
	is_verified BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_user_email ON "user" (email);

CREATE TABLE accesstoken (
	user_id UUID NOT NULL,
	token VARCHAR(43) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (token),
	FOREIGN KEY(user_id) REFERENCES "user" (id) ON DELETE cascade
);

CREATE INDEX ix_accesstoken_created_at ON accesstoken (created_at);

CREATE TABLE workspace (
	name VARCHAR(120) NOT NULL,
	owner_id UUID NOT NULL,
	balance_milli BIGINT NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (balance_milli >= 0),
	FOREIGN KEY(owner_id) REFERENCES "user" (id)
);

CREATE TABLE membership (
	workspace_id UUID NOT NULL,
	user_id UUID NOT NULL,
	role VARCHAR(20) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (workspace_id, user_id),
	CHECK (role IN ('owner', 'editor', 'viewer')),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id),
	FOREIGN KEY(user_id) REFERENCES "user" (id)
);

CREATE INDEX ix_membership_workspace_id ON membership (workspace_id);

CREATE INDEX ix_membership_user_id ON membership (user_id);

CREATE TABLE project (
	name VARCHAR(160) NOT NULL,
	description VARCHAR NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_project_workspace_id ON project (workspace_id);

CREATE TABLE reservation (
	operation_key VARCHAR NOT NULL,
	amount_milli BIGINT NOT NULL,
	settled_milli BIGINT NOT NULL,
	state VARCHAR NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (amount_milli >= 0 AND settled_milli >= 0 AND settled_milli <= amount_milli),
	UNIQUE (operation_key),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_reservation_workspace_id ON reservation (workspace_id);

CREATE TABLE asset (
	project_id UUID NOT NULL,
	name VARCHAR(255) NOT NULL,
	source_root VARCHAR NOT NULL,
	relative_path VARCHAR NOT NULL,
	source_kind VARCHAR NOT NULL,
	fingerprint VARCHAR(64),
	source_size BIGINT NOT NULL,
	source_mtime_ns BIGINT NOT NULL,
	duration_us BIGINT,
	status VARCHAR NOT NULL,
	error VARCHAR,
	proxy_path VARCHAR,
	thumbnail_path VARCHAR,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (project_id, source_root, relative_path),
	FOREIGN KEY(project_id) REFERENCES project (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_asset_project_id ON asset (project_id);

CREATE INDEX ix_asset_workspace_id ON asset (workspace_id);

CREATE INDEX ix_asset_fingerprint ON asset (fingerprint);

CREATE TABLE collection (
	project_id UUID NOT NULL,
	name VARCHAR(160) NOT NULL,
	instructions VARCHAR NOT NULL,
	saved_query VARCHAR,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES project (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_collection_workspace_id ON collection (workspace_id);

CREATE INDEX ix_collection_project_id ON collection (project_id);

CREATE TABLE ledger_entry (
	operation_key VARCHAR NOT NULL,
	reservation_id UUID,
	kind VARCHAR NOT NULL,
	delta_milli BIGINT NOT NULL,
	balance_milli BIGINT NOT NULL,
	description VARCHAR NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (operation_key),
	FOREIGN KEY(reservation_id) REFERENCES reservation (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_ledger_entry_workspace_id ON ledger_entry (workspace_id);

CREATE TABLE analysis_run (
	asset_id UUID NOT NULL,
	operation_key VARCHAR NOT NULL,
	model VARCHAR NOT NULL,
	prompt_version VARCHAR NOT NULL,
	preprocessing_version VARCHAR NOT NULL,
	schema_version VARCHAR NOT NULL,
	transcript_version VARCHAR NOT NULL,
	sampling JSONB NOT NULL,
	status VARCHAR NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(asset_id) REFERENCES asset (id),
	UNIQUE (operation_key),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_analysis_run_workspace_id ON analysis_run (workspace_id);

CREATE INDEX ix_analysis_run_asset_id ON analysis_run (asset_id);

CREATE TABLE collection_item (
	collection_id UUID NOT NULL,
	asset_id UUID NOT NULL,
	start_us BIGINT,
	end_us BIGINT,
	note VARCHAR NOT NULL,
	position INTEGER NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK ((start_us IS NULL AND end_us IS NULL) OR (start_us IS NOT NULL AND end_us IS NOT NULL AND start_us >= 0 AND end_us > start_us)),
	FOREIGN KEY(collection_id) REFERENCES collection (id),
	FOREIGN KEY(asset_id) REFERENCES asset (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_collection_item_workspace_id ON collection_item (workspace_id);

CREATE INDEX ix_collection_item_collection_id ON collection_item (collection_id);

CREATE TABLE job (
	project_id UUID NOT NULL,
	asset_id UUID,
	kind VARCHAR NOT NULL,
	state VARCHAR NOT NULL,
	stage VARCHAR NOT NULL,
	progress INTEGER NOT NULL,
	workflow_id VARCHAR NOT NULL,
	payload JSONB NOT NULL,
	error VARCHAR,
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES project (id),
	FOREIGN KEY(asset_id) REFERENCES asset (id),
	UNIQUE (workflow_id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_job_project_id ON job (project_id);

CREATE INDEX ix_job_workspace_id ON job (workspace_id);

CREATE TABLE media_timeline (
	asset_id UUID NOT NULL,
	kind VARCHAR NOT NULL,
	details JSONB NOT NULL,
	mapping JSONB NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (asset_id, kind),
	FOREIGN KEY(asset_id) REFERENCES asset (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_media_timeline_asset_id ON media_timeline (asset_id);

CREATE INDEX ix_media_timeline_workspace_id ON media_timeline (workspace_id);

CREATE TABLE shot (
	asset_id UUID NOT NULL,
	start_us BIGINT NOT NULL,
	end_us BIGINT NOT NULL,
	producer VARCHAR NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (start_us >= 0 AND end_us > start_us),
	UNIQUE (asset_id, start_us, end_us),
	FOREIGN KEY(asset_id) REFERENCES asset (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_shot_workspace_id ON shot (workspace_id);

CREATE INDEX ix_shot_asset_id ON shot (asset_id);

CREATE TABLE usage (
	asset_id UUID,
	operation_key VARCHAR NOT NULL,
	kind VARCHAR NOT NULL,
	model VARCHAR,
	duration_us BIGINT NOT NULL,
	input_tokens INTEGER NOT NULL,
	output_tokens INTEGER NOT NULL,
	bytes BIGINT NOT NULL,
	attempts INTEGER NOT NULL,
	provider_outcome VARCHAR NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(asset_id) REFERENCES asset (id),
	UNIQUE (operation_key),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_usage_workspace_id ON usage (workspace_id);

CREATE TABLE analysis_window (
	run_id UUID NOT NULL,
	asset_id UUID NOT NULL,
	start_us BIGINT NOT NULL,
	end_us BIGINT NOT NULL,
	cache_key VARCHAR NOT NULL,
	state VARCHAR NOT NULL,
	raw_response JSONB,
	provider_file VARCHAR,
	error VARCHAR,
	attempts INTEGER NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (start_us >= 0 AND end_us > start_us),
	FOREIGN KEY(run_id) REFERENCES analysis_run (id),
	FOREIGN KEY(asset_id) REFERENCES asset (id),
	UNIQUE (cache_key),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_analysis_window_workspace_id ON analysis_window (workspace_id);

CREATE INDEX ix_analysis_window_run_id ON analysis_window (run_id);

CREATE INDEX ix_analysis_window_asset_id ON analysis_window (asset_id);

CREATE TABLE export (
	project_id UUID NOT NULL,
	job_id UUID NOT NULL,
	kind VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	plan JSONB NOT NULL,
	state VARCHAR NOT NULL,
	output_path VARCHAR,
	provenance JSONB NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(project_id) REFERENCES project (id),
	UNIQUE (job_id),
	FOREIGN KEY(job_id) REFERENCES job (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_export_project_id ON export (project_id);

CREATE INDEX ix_export_workspace_id ON export (workspace_id);

CREATE TABLE processing_event (
	job_id UUID NOT NULL,
	kind VARCHAR NOT NULL,
	message VARCHAR NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(job_id) REFERENCES job (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_processing_event_workspace_id ON processing_event (workspace_id);

CREATE INDEX ix_processing_event_job_id ON processing_event (job_id);

CREATE TABLE observation (
	asset_id UUID NOT NULL,
	timeline_id UUID NOT NULL,
	run_id UUID,
	window_id UUID,
	operation_key VARCHAR NOT NULL,
	kind VARCHAR NOT NULL,
	start_us BIGINT NOT NULL,
	end_us BIGINT NOT NULL,
	proposed_start_us BIGINT NOT NULL,
	proposed_end_us BIGINT NOT NULL,
	description VARCHAR NOT NULL,
	attributes JSONB NOT NULL,
	evidence JSONB NOT NULL,
	producer VARCHAR NOT NULL,
	model VARCHAR NOT NULL,
	prompt_version VARCHAR NOT NULL,
	preprocessing_version VARCHAR NOT NULL,
	review_status VARCHAR NOT NULL,
	uncertainty VARCHAR NOT NULL,
	version INTEGER NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CHECK (start_us >= 0 AND end_us > start_us),
	CHECK (proposed_start_us >= 0 AND proposed_end_us > proposed_start_us),
	FOREIGN KEY(asset_id) REFERENCES asset (id),
	FOREIGN KEY(timeline_id) REFERENCES media_timeline (id),
	FOREIGN KEY(run_id) REFERENCES analysis_run (id),
	FOREIGN KEY(window_id) REFERENCES analysis_window (id),
	UNIQUE (operation_key),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_observation_workspace_id ON observation (workspace_id);

CREATE INDEX observation_asset_time ON observation (asset_id, start_us);

CREATE INDEX ix_observation_asset_id ON observation (asset_id);

CREATE TABLE embedding (
	observation_id UUID NOT NULL,
	model VARCHAR NOT NULL,
	dimension INTEGER NOT NULL,
	text_hash VARCHAR NOT NULL,
	vector VECTOR NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (observation_id, model),
	FOREIGN KEY(observation_id) REFERENCES observation (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_embedding_workspace_id ON embedding (workspace_id);

CREATE INDEX ix_embedding_observation_id ON embedding (observation_id);

CREATE TABLE observation_revision (
	observation_id UUID NOT NULL,
	user_id UUID NOT NULL,
	version INTEGER NOT NULL,
	before JSONB NOT NULL,
	after JSONB NOT NULL,
	workspace_id UUID NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (observation_id, version),
	FOREIGN KEY(observation_id) REFERENCES observation (id),
	FOREIGN KEY(user_id) REFERENCES "user" (id),
	FOREIGN KEY(workspace_id) REFERENCES workspace (id)
);

CREATE INDEX ix_observation_revision_workspace_id ON observation_revision (workspace_id);

CREATE INDEX ix_observation_revision_observation_id ON observation_revision (observation_id);

ALTER TABLE "project" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "project" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "project" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "reservation" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "reservation" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "reservation" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "asset" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "asset" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "asset" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "collection" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "collection" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "collection" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "ledger_entry" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "ledger_entry" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "ledger_entry" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "analysis_run" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "analysis_run" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "analysis_run" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "collection_item" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "collection_item" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "collection_item" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "job" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "job" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "job" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "media_timeline" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "media_timeline" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "media_timeline" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "shot" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "shot" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "shot" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "usage" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "usage" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "usage" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "analysis_window" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "analysis_window" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "analysis_window" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "export" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "export" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "export" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "processing_event" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "processing_event" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "processing_event" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "observation" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "observation" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "observation" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "embedding" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "embedding" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "embedding" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

ALTER TABLE "observation_revision" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "observation_revision" FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "observation_revision" USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid) WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);

CREATE INDEX observation_text_search ON observation USING gin (to_tsvector('english', description));

GRANT USAGE ON SCHEMA public TO rushes_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rushes_app;

REVOKE ALL ON alembic_version FROM rushes_app;
