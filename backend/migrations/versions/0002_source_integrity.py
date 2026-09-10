"""Preserve selected paths, mark duplicates, and enforce same-tenant references."""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.execute("ALTER TABLE asset ADD COLUMN import_relative_path TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE asset ADD COLUMN duplicate_of_id UUID REFERENCES asset(id)")
    op.execute("UPDATE asset SET import_relative_path=relative_path")
    op.execute(
        'ALTER TABLE "analysis_run" ADD CONSTRAINT "analysis_run_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "analysis_window" ADD CONSTRAINT "analysis_window_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "asset" ADD CONSTRAINT "asset_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "collection" ADD CONSTRAINT "collection_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "collection_item" ADD CONSTRAINT "collection_item_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "embedding" ADD CONSTRAINT "embedding_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "export" ADD CONSTRAINT "export_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute('ALTER TABLE "job" ADD CONSTRAINT "job_tenant_identity" UNIQUE (id, workspace_id)')
    op.execute(
        'ALTER TABLE "ledger_entry" ADD CONSTRAINT "ledger_entry_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "media_timeline" ADD CONSTRAINT "media_timeline_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "observation" ADD CONSTRAINT "observation_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "observation_revision" ADD CONSTRAINT "observation_revision_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "processing_event" ADD CONSTRAINT "processing_event_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "project" ADD CONSTRAINT "project_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "reservation" ADD CONSTRAINT "reservation_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute('ALTER TABLE "shot" ADD CONSTRAINT "shot_tenant_identity" UNIQUE (id, workspace_id)')
    op.execute(
        'ALTER TABLE "usage" ADD CONSTRAINT "usage_tenant_identity" UNIQUE (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "asset" ADD CONSTRAINT "asset_project_id_tenant_fk" FOREIGN KEY ("project_id", workspace_id) REFERENCES "project" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "asset" ADD CONSTRAINT "asset_duplicate_of_id_tenant_fk" FOREIGN KEY ("duplicate_of_id", workspace_id) REFERENCES "asset" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "collection" ADD CONSTRAINT "collection_project_id_tenant_fk" FOREIGN KEY ("project_id", workspace_id) REFERENCES "project" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "ledger_entry" ADD CONSTRAINT "ledger_entry_reservation_id_tenant_fk" FOREIGN KEY ("reservation_id", workspace_id) REFERENCES "reservation" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "analysis_run" ADD CONSTRAINT "analysis_run_asset_id_tenant_fk" FOREIGN KEY ("asset_id", workspace_id) REFERENCES "asset" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "collection_item" ADD CONSTRAINT "collection_item_collection_id_tenant_fk" FOREIGN KEY ("collection_id", workspace_id) REFERENCES "collection" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "collection_item" ADD CONSTRAINT "collection_item_asset_id_tenant_fk" FOREIGN KEY ("asset_id", workspace_id) REFERENCES "asset" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "job" ADD CONSTRAINT "job_project_id_tenant_fk" FOREIGN KEY ("project_id", workspace_id) REFERENCES "project" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "job" ADD CONSTRAINT "job_asset_id_tenant_fk" FOREIGN KEY ("asset_id", workspace_id) REFERENCES "asset" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "media_timeline" ADD CONSTRAINT "media_timeline_asset_id_tenant_fk" FOREIGN KEY ("asset_id", workspace_id) REFERENCES "asset" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "shot" ADD CONSTRAINT "shot_asset_id_tenant_fk" FOREIGN KEY ("asset_id", workspace_id) REFERENCES "asset" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "usage" ADD CONSTRAINT "usage_asset_id_tenant_fk" FOREIGN KEY ("asset_id", workspace_id) REFERENCES "asset" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "analysis_window" ADD CONSTRAINT "analysis_window_run_id_tenant_fk" FOREIGN KEY ("run_id", workspace_id) REFERENCES "analysis_run" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "analysis_window" ADD CONSTRAINT "analysis_window_asset_id_tenant_fk" FOREIGN KEY ("asset_id", workspace_id) REFERENCES "asset" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "export" ADD CONSTRAINT "export_project_id_tenant_fk" FOREIGN KEY ("project_id", workspace_id) REFERENCES "project" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "export" ADD CONSTRAINT "export_job_id_tenant_fk" FOREIGN KEY ("job_id", workspace_id) REFERENCES "job" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "processing_event" ADD CONSTRAINT "processing_event_job_id_tenant_fk" FOREIGN KEY ("job_id", workspace_id) REFERENCES "job" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "observation" ADD CONSTRAINT "observation_asset_id_tenant_fk" FOREIGN KEY ("asset_id", workspace_id) REFERENCES "asset" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "observation" ADD CONSTRAINT "observation_timeline_id_tenant_fk" FOREIGN KEY ("timeline_id", workspace_id) REFERENCES "media_timeline" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "observation" ADD CONSTRAINT "observation_run_id_tenant_fk" FOREIGN KEY ("run_id", workspace_id) REFERENCES "analysis_run" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "observation" ADD CONSTRAINT "observation_window_id_tenant_fk" FOREIGN KEY ("window_id", workspace_id) REFERENCES "analysis_window" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "embedding" ADD CONSTRAINT "embedding_observation_id_tenant_fk" FOREIGN KEY ("observation_id", workspace_id) REFERENCES "observation" (id, workspace_id)'
    )
    op.execute(
        'ALTER TABLE "observation_revision" ADD CONSTRAINT "observation_revision_observation_id_tenant_fk" FOREIGN KEY ("observation_id", workspace_id) REFERENCES "observation" (id, workspace_id)'
    )


def downgrade():
    raise RuntimeError("Restore a backup to remove tenant-integrity constraints safely.")
