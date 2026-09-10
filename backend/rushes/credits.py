from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rushes.config import settings
from rushes.models import LedgerEntry, Reservation, Workspace


class CreditError(ValueError):
    pass


def estimate_milli(duration_us: int) -> int:
    return (duration_us * settings().credits_per_minute * 1000 + 59_999_999) // 60_000_000


async def reserve(
    db: AsyncSession, workspace_id: UUID, operation: str, amount: int, *, resume=False
) -> Reservation:
    if amount < 0 or amount > settings().max_analysis_credits * 1000:
        raise CreditError("Analysis exceeds the configured per-request spending cap")
    workspace = await db.scalar(
        select(Workspace).where(Workspace.id == workspace_id).with_for_update()
    )
    existing = await db.scalar(
        select(Reservation).where(
            Reservation.operation_key == operation, Reservation.workspace_id == workspace_id
        )
    )
    if existing:
        if existing.amount_milli != amount:
            raise CreditError("Operation already reserved with a different estimate")
        if resume and existing.state != "reserved":
            remaining = amount - existing.settled_milli
            if workspace.balance_milli < remaining:
                raise CreditError("Insufficient credits to resume the remaining analysis")
            workspace.balance_milli -= remaining
            existing.cycle += 1
            existing.state = "reserved"
            db.add(
                LedgerEntry(
                    workspace_id=workspace_id,
                    reservation_id=existing.id,
                    operation_key=f"reserve:{operation}:{existing.cycle}",
                    kind="reservation",
                    delta_milli=-remaining,
                    balance_milli=workspace.balance_milli,
                    description="Resumed unused portion of the original analysis estimate",
                )
            )
        return existing
    if workspace.balance_milli < amount:
        raise CreditError("Insufficient local development credits")
    workspace.balance_milli -= amount
    reservation = Reservation(
        workspace_id=workspace_id, operation_key=operation, amount_milli=amount
    )
    db.add(reservation)
    await db.flush()
    db.add(
        LedgerEntry(
            workspace_id=workspace_id,
            reservation_id=reservation.id,
            operation_key=f"reserve:{operation}",
            kind="reservation",
            delta_milli=-amount,
            balance_milli=workspace.balance_milli,
            description="Reserved estimated analysis credits",
        )
    )
    return reservation


async def settle(db: AsyncSession, workspace_id: UUID, operation: str, actual: int):
    workspace = await db.scalar(
        select(Workspace).where(Workspace.id == workspace_id).with_for_update()
    )
    reservation = await db.scalar(
        select(Reservation)
        .where(Reservation.operation_key == operation, Reservation.workspace_id == workspace_id)
        .with_for_update()
    )
    if reservation is None:
        raise CreditError("No reservation exists for this operation")
    if reservation.state != "reserved":
        if reservation.settled_milli != actual:
            raise CreditError("Operation was already settled with a different actual amount")
        return
    if not reservation.settled_milli <= actual <= reservation.amount_milli:
        raise CreditError("Settlement must fit its reservation")
    refund = reservation.amount_milli - actual
    workspace.balance_milli += refund
    reservation.state = "released" if actual == 0 else "settled"
    reservation.settled_milli = actual
    db.add(
        LedgerEntry(
            workspace_id=workspace_id,
            reservation_id=reservation.id,
            operation_key=f"settle:{operation}"
            + (f":{reservation.cycle}" if reservation.cycle else ""),
            kind=reservation.state,
            delta_milli=refund,
            balance_milli=workspace.balance_milli,
            description=f"Analysis settled at {actual / 1000:g} credits; unused reservation released",
        )
    )
