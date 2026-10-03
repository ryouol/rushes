"""Current evidence policy for retrieval, review, and worklog exports."""

from sqlalchemy import func, or_, select

from rushes.models import AnalysisRun, Observation


def current_observation():
    """Keep run-independent evidence, human corrections, and the latest attempt.

    A running/partial/failed replacement does not make older machine claims current
    again. Their rows and provenance remain available through explicit history.
    """
    latest = (
        select(AnalysisRun.id)
        .where(
            AnalysisRun.workspace_id == Observation.workspace_id,
            AnalysisRun.asset_id == Observation.asset_id,
        )
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .limit(1)
        .correlate(Observation)
        .scalar_subquery()
    )
    return or_(
        Observation.run_id.is_(None),
        Observation.review_status == "corrected",
        func.coalesce(Observation.run_id == latest, False),
    )
