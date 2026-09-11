"""Google identities and short-lived, browser-bound OAuth attempts."""

from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade():
    op.execute("""
        CREATE TABLE google_identity (
            subject VARCHAR(255) PRIMARY KEY,
            user_id UUID NOT NULL UNIQUE REFERENCES "user"(id) ON DELETE CASCADE,
            email VARCHAR(320) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE oauth_attempt (
            state_hash VARCHAR(64) PRIMARY KEY,
            browser_hash VARCHAR(64) NOT NULL,
            nonce VARCHAR(43) NOT NULL,
            verifier VARCHAR(43) NOT NULL,
            destination VARCHAR(2048) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            link_session_token VARCHAR(43) REFERENCES accesstoken(token) ON DELETE CASCADE
        );
        CREATE INDEX ix_oauth_attempt_expires_at ON oauth_attempt(expires_at);
        CREATE INDEX ix_oauth_attempt_link_session_token ON oauth_attempt(link_session_token);
        REVOKE ALL ON google_identity, oauth_attempt FROM PUBLIC;
        GRANT SELECT, INSERT, UPDATE, DELETE ON google_identity, oauth_attempt TO rushes_app;
    """)


def downgrade():
    raise RuntimeError(
        "Removing linked login identities requires an explicit account-access decision"
    )
