"""Retain versioned human category reviews independently of analysis runs."""

from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade():
    op.execute("""
        CREATE TABLE asset_category_review (
            id UUID PRIMARY KEY,
            workspace_id UUID NOT NULL REFERENCES workspace(id),
            asset_id UUID NOT NULL REFERENCES asset(id),
            user_id UUID NOT NULL REFERENCES "user"(id),
            version INTEGER NOT NULL CHECK (version > 0),
            categories JSONB CHECK (categories IS NULL OR jsonb_typeof(categories) = 'array'),
            created_at TIMESTAMPTZ NOT NULL,
            UNIQUE (asset_id, version),
            FOREIGN KEY (asset_id, workspace_id) REFERENCES asset(id, workspace_id)
        );
        CREATE INDEX ix_asset_category_review_workspace_id ON asset_category_review(workspace_id);
        ALTER TABLE asset_category_review ENABLE ROW LEVEL SECURITY;
        ALTER TABLE asset_category_review FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON asset_category_review
            USING (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid)
            WITH CHECK (workspace_id = NULLIF(current_setting('rushes.workspace_id', true), '')::uuid);
        GRANT SELECT, INSERT, DELETE ON asset_category_review TO rushes_app;
    """)


def downgrade():
    raise RuntimeError("Removing human category history requires an explicit retention decision")
