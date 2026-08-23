"""
Mandate endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_db
from src.models.payment_mandate import PaymentMandate
from src.schemas.mandates import MandateSetupRequest, MandateSetupResponse, MandateStatusResponse
from src.adapters.factory import GatewayAdapterFactory

router = APIRouter(prefix="/payments/mandates", tags=["mandates"])

@router.post("", response_model=MandateSetupResponse)
async def setup_mandate(
    request: MandateSetupRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Setup a new payment mandate (e.g., Raast auto-debit).
    """
    if request.gateway not in ["raast", "jazzcash"]:
        raise HTTPException(status_code=400, detail="Unsupported gateway for mandates")

    adapter = GatewayAdapterFactory.get(request.gateway)
    if not hasattr(adapter.client, "setup_mandate"):
        raise HTTPException(status_code=400, detail="Gateway does not support mandates")

    result = adapter.client.setup_mandate(
        user_id=current_user.id,
        payer_iban=request.payer_identifier,
        max_amount=request.max_amount_per_txn or 0
    )

    mandate = PaymentMandate(
        user_id=current_user.id,
        gateway=request.gateway,
        mandate_reference=result["mandate_reference"],
        status="initiated",
        payer_identifier=request.payer_identifier,
        max_amount_per_txn=request.max_amount_per_txn,
    )
    db.add(mandate)
    await db.commit()

    return MandateSetupResponse(
        mandate_id=mandate.id,
        status="initiated",
        mandate_reference=mandate.mandate_reference,
        payer_identifier=mandate.payer_identifier,
        authorization_url=result.get("authorization_url"),
        message="Mandate setup initiated. Please authorize via your banking app."
    )

@router.get("/", response_model=list[MandateStatusResponse])
async def list_mandates(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active mandates for the user."""
    result = await db.execute(
        select(PaymentMandate).where(PaymentMandate.user_id == current_user.id)
    )
    mandates = result.scalars().all()
    return [
        MandateStatusResponse(
            mandate_reference=m.mandate_reference,
            gateway=m.gateway,
            status=m.status,
            payer_identifier=m.payer_identifier,
            max_amount_per_txn=m.max_amount_per_txn,
            expires_at=m.expires_at,
            last_used_at=m.last_used_at,
        ) for m in mandates
    ]

@router.delete("/{mandate_id}")
async def revoke_mandate(
    mandate_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an active mandate."""
    mandate = await db.scalar(
        select(PaymentMandate).where(
            PaymentMandate.id == mandate_id,
            PaymentMandate.user_id == current_user.id
        )
    )
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")

    mandate.status = "revoked"
    from datetime import datetime, timezone
    mandate.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {"status": "revoked", "mandate_id": mandate_id}


@router.post("/setup", response_model=MandateSetupResponse, include_in_schema=False)
async def setup_mandate_legacy(
    request: MandateSetupRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Backward-compatible alias for legacy clients."""
    return await setup_mandate(request=request, current_user=current_user, db=db)


@router.post("/{mandate_reference}/revoke", include_in_schema=False)
async def revoke_mandate_legacy(
    mandate_reference: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Backward-compatible alias for legacy clients."""
    mandate = await db.scalar(
        select(PaymentMandate).where(
            PaymentMandate.mandate_reference == mandate_reference,
            PaymentMandate.user_id == current_user.id
        )
    )
    if not mandate:
        raise HTTPException(status_code=404, detail="Mandate not found")
    return await revoke_mandate(mandate_id=mandate.id, current_user=current_user, db=db)
