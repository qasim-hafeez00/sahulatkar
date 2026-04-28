from __future__ import annotations
from datetime import date

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.dependencies import RequestContext, get_redis, require_admin_role, require_internal_request
from src.events.dlq import EventDeadLetterQueue
from src.schemas.finance import (
    ARAgingResponse,
    ARAgingDetailResponse,
    AccountBalanceResponse,
    BalanceSheetResponse,
    CashFlowResponse,
    CharityDisbursementRequest,
    CharityDisbursementResponse,
    CharityReportResponse,
    CharityAutoAllocationResponse,
    DLQListResponse,
    DLQMessageResponse,
    DLQRetryResponse,
    JournalEntryListResponse,
    JournalEntryResponse,
    LedgerAccountsListResponse,
    OverdueReportResponse,
    PeriodCloseAlertResponse,
    ProfitLossResponse,
    PeriodManagementResponse,
    ReconciliationImportRequest,
    ReconciliationImportResponse,
    ReconciliationListResponse,
    ReconciliationOverrideRequest,
    ReconciliationOverrideResponse,
    ShariahAuditResponse,
    TasdeeqReportResponse,
    TrialBalanceResponse,
    FiscalYearSeedRequest,
)
from src.services.accounting_service import AccountingService
from src.services.charity_service import CharityService
from src.services.reconciliation_service import ReconciliationService
from src.services.period_service import PeriodService
from src.services.tasdeeq_service import TasdeeqService
from src.billing.billing_sweep import BillingSweepService
from sk_shared.events import build_event_envelope, event_channel
from sk_shared.redis_client import RedisClient


router = APIRouter()


@router.get("/admin/finance/pl", response_model=ProfitLossResponse)
async def get_profit_loss(
    period: str,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db, redis=redis)
    try:
        return await service.build_profit_loss_report(period)
    except ValueError as exc:
        if str(exc) == "INVALID_PERIOD_FORMAT":
            raise HTTPException(status_code=422, detail="INVALID_PERIOD_FORMAT") from exc
        raise


@router.get("/admin/finance/trial-balance", response_model=TrialBalanceResponse)
async def get_trial_balance(
    period: str,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db, redis=redis)
    try:
        return await service.get_trial_balance(period)
    except ValueError as exc:
        if str(exc) == "INVALID_PERIOD_FORMAT":
            raise HTTPException(status_code=422, detail="INVALID_PERIOD_FORMAT") from exc
        raise


@router.get("/admin/finance/balance-sheet", response_model=BalanceSheetResponse)
async def get_balance_sheet(
    as_of: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db, redis=redis)
    try:
        return await service.build_balance_sheet(as_of=as_of)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="INVALID_AS_OF_DATE") from exc


@router.get("/admin/finance/accounts", response_model=LedgerAccountsListResponse)
async def get_ledger_accounts(
    account_type: str | None = Query(default=None),
    as_of: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db, redis=redis)
    try:
        return await service.list_accounts(account_type=account_type, as_of=as_of)
    except ValueError as exc:
        if str(exc) == "INVALID_AS_OF_DATE":
            raise HTTPException(status_code=422, detail="INVALID_AS_OF_DATE") from exc
        if str(exc) == "INVALID_ACCOUNT_TYPE":
            raise HTTPException(status_code=422, detail="INVALID_ACCOUNT_TYPE") from exc
        raise


@router.get("/admin/finance/accounts/{account_code}/balance", response_model=AccountBalanceResponse)
async def get_ledger_account_balance(
    account_code: str,
    as_of: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db, redis=redis)
    try:
        return await service.get_account_balance(account_code=account_code, as_of=as_of)
    except ValueError as exc:
        if str(exc) == "INVALID_AS_OF_DATE":
            raise HTTPException(status_code=422, detail="INVALID_AS_OF_DATE") from exc
        raise
    except LookupError as exc:
        if str(exc) == "ACCOUNT_NOT_FOUND":
            raise HTTPException(status_code=404, detail="ACCOUNT_NOT_FOUND") from exc
        raise


@router.get("/admin/finance/entries", response_model=JournalEntryListResponse)
async def get_journal_entries(
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db, redis=redis)
    try:
        return await service.list_journal_entries(
            from_date=from_date,
            to_date=to_date,
            entry_type=entry_type,
            source_type=source_type,
            cursor=cursor,
            limit=limit,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="INVALID_DATE_FILTER")


@router.get("/admin/finance/entries/{entry_number}", response_model=JournalEntryResponse)
async def get_journal_entry_detail(
    entry_number: str,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db, redis=redis)
    try:
        return await service.get_journal_entry(entry_number=entry_number)
    except LookupError as exc:
        if str(exc) == "ENTRY_NOT_FOUND":
            raise HTTPException(status_code=404, detail="ENTRY_NOT_FOUND") from exc
        raise


@router.get("/admin/finance/ar-aging", response_model=ARAgingResponse)
async def get_ar_aging(
    as_of: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    plan_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db, redis=redis)
    try:
        return await service.build_ar_aging_report(
            as_of=as_of,
            user_id=user_id,
            plan_type=plan_type,
            status=status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="INVALID_AS_OF_DATE") from exc


@router.get("/admin/finance/dlq", response_model=DLQListResponse)
async def get_dlq_messages(
    limit: int = Query(default=50, ge=1, le=500),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    dlq = EventDeadLetterQueue()
    messages = await dlq.get_messages()
    mapped: list[dict[str, object]] = []
    for idx, message in enumerate(messages, start=1):
        mapped.append(
            {
                "message_id": idx,
                "event_name": message.event_name,
                "payload": message.payload,
                "error_type": message.error_type,
                "error_message": message.error_message,
                "timestamp": message.timestamp,
                "retry_count": message.retry_count,
            }
        )

    mapped.sort(key=lambda item: item["timestamp"], reverse=True)
    return {
        "total_messages": len(mapped),
        "items": mapped[:limit],
    }


@router.get("/admin/finance/dlq/{message_id}", response_model=DLQMessageResponse)
async def get_dlq_message_detail(
    message_id: int,
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    if message_id < 1:
        raise HTTPException(status_code=404, detail="DLQ_MESSAGE_NOT_FOUND")

    dlq = EventDeadLetterQueue()
    messages = await dlq.get_messages()
    if message_id > len(messages):
        raise HTTPException(status_code=404, detail="DLQ_MESSAGE_NOT_FOUND")

    message = messages[message_id - 1]
    return {
        "message_id": message_id,
        "event_name": message.event_name,
        "payload": message.payload,
        "error_type": message.error_type,
        "error_message": message.error_message,
        "timestamp": message.timestamp,
        "retry_count": message.retry_count,
    }


@router.post("/admin/finance/dlq/{message_id}/retry", response_model=DLQRetryResponse)
async def retry_dlq_message(
    message_id: int,
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["super_admin"])),
) -> dict[str, object]:
    if message_id < 1:
        raise HTTPException(status_code=404, detail="DLQ_MESSAGE_NOT_FOUND")

    dlq = EventDeadLetterQueue()
    messages = await dlq.get_messages()
    if message_id > len(messages):
        raise HTTPException(status_code=404, detail="DLQ_MESSAGE_NOT_FOUND")

    message = messages[message_id - 1]
    payload = message.payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            payload_dict = parsed if isinstance(parsed, dict) else {"raw_payload": payload}
        except json.JSONDecodeError:
            payload_dict = {"raw_payload": payload}
    else:
        payload_dict = payload

    envelope = build_event_envelope(
        event=message.event_name,
        source_service="ledger-service",
        payload=payload_dict,
    )
    await redis.publish(event_channel(message.event_name), envelope.to_json())

    return {
        "message_id": message_id,
        "event_name": message.event_name,
        "status": "requeued",
    }


@router.get("/admin/finance/reconciliation", response_model=ReconciliationListResponse)
async def get_reconciliation(
    gateway: str | None = Query(default=None),
    settlement_date: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = ReconciliationService(db, redis=redis)
    try:
        return await service.query_snapshots(gateway=gateway, settlement_date=settlement_date, page=page, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="INVALID_SETTLEMENT_DATE") from exc


@router.get("/admin/finance/shariah-audit", response_model=ShariahAuditResponse)
async def get_shariah_audit(
    period: str,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = AccountingService(db, redis=redis)
    try:
        return await service.build_shariah_audit_report(period)
    except ValueError as exc:
        if str(exc) == "INVALID_PERIOD_FORMAT":
            raise HTTPException(status_code=422, detail="INVALID_PERIOD_FORMAT") from exc
        raise


@router.post("/admin/finance/reconciliation", response_model=ReconciliationImportResponse)
async def import_reconciliation(
    request: ReconciliationImportRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_internal_request),
) -> dict[str, object]:
    service = ReconciliationService(db, redis=redis)
    return await service.import_snapshot(
        gateway=request.gateway,
        settlement_date=request.settlement_date.isoformat(),
        expected_amount=request.expected_amount,
        actual_amount=request.actual_amount,
        reference=request.reference,
        notes=request.notes,
    )


@router.post("/admin/finance/reconciliation/{reconciliation_id}/override", response_model=ReconciliationOverrideResponse)
async def manual_reconciliation_override(
    reconciliation_id: int,
    request: ReconciliationOverrideRequest,
    db: AsyncSession = Depends(get_db),
    ctx: RequestContext = Depends(require_admin_role(["super_admin"])),
) -> dict[str, object]:
    """Force-match a discrepant reconciliation (super admin only)."""
    service = ReconciliationService(db)
    try:
        return await service.manual_override(
            reconciliation_id=reconciliation_id,
            reason=request.reason,
            admin_user=ctx.user_id,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/finance/cash-flow", response_model=CashFlowResponse)
async def get_cash_flow(
    period: str,
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    """P3-01: Cash Flow Statement (Direct Method)."""
    service = AccountingService(db)
    try:
        return await service.build_cash_flow_statement(period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/admin/finance/ar-aging/export", response_model=list[ARAgingDetailResponse])
async def export_ar_aging_details(
    as_of: str | None = None,
    min_days_overdue: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> list[dict[str, object]]:
    """P3-02: AR aging detail export for granular analysis."""
    service = AccountingService(db)
    try:
        return await service.get_ar_aging_details(
            as_of=as_of,
            min_days_overdue=min_days_overdue,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/admin/finance/periods/seed", response_model=list[PeriodManagementResponse])
async def seed_periods(
    request: FiscalYearSeedRequest,
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["super_admin"])),
) -> list[dict[str, object]]:
    """P3-03: Seed 12 monthly periods for a fiscal year."""
    service = PeriodService(db)
    periods = await service.seed_fiscal_year(request.year)
    await db.commit()
    return [
        {
            "period_key": p.period_key,
            "status": p.status,
            "fiscal_year": p.fiscal_year,
        }
        for p in periods
    ]


@router.post("/admin/finance/periods/{period_key}/close", response_model=PeriodManagementResponse)
async def close_period(
    period_key: str,
    db: AsyncSession = Depends(get_db),
    ctx: RequestContext = Depends(require_admin_role(["super_admin"])),
) -> dict[str, object]:
    """P3-03: Close an accounting period."""
    service = PeriodService(db)
    try:
        period = await service.close_period(period_key, closed_by=str(ctx.user_id))
        await db.commit()
        return {
            "period_key": period.period_key,
            "status": period.status,
            "fiscal_year": period.fiscal_year,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/admin/finance/periods/{period_key}/reopen", response_model=PeriodManagementResponse)
async def reopen_period(
    period_key: str,
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["super_admin"])),
) -> dict[str, object]:
    """P3-03: Reopen a closed accounting period."""
    service = PeriodService(db)
    period = await service.reopen_period(period_key)
    await db.commit()
    return {
        "period_key": period.period_key,
        "status": period.status,
        "fiscal_year": period.fiscal_year,
    }


@router.get("/admin/finance/charity-report", response_model=CharityReportResponse)
async def get_charity_report(
    period: str,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    service = CharityService(db, redis=redis)
    try:
        return await service.get_charity_summary(period)
    except ValueError as exc:
        if str(exc) == "INVALID_PERIOD_FORMAT":
            raise HTTPException(status_code=422, detail="INVALID_PERIOD_FORMAT") from exc
        raise


from src.core.rate_limit import rate_limit_admin_writes

@router.post("/admin/finance/charity-disbursement", response_model=CharityDisbursementResponse)
async def post_charity_disbursement(
    request: CharityDisbursementRequest,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["super_admin"])),
    __: bool = Depends(rate_limit_admin_writes),
) -> dict[str, object]:
    service = CharityService(db, redis=redis)
    return await service.record_disbursement(
        allocation_ids=request.allocation_ids,
        payment_reference=request.payment_reference,
        receipt_s3=request.receipt_s3,
    )


@router.post("/admin/finance/billing-sweep")
async def trigger_billing_sweep(
    as_of: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["super_admin"])),
    __: bool = Depends(rate_limit_admin_writes),
) -> dict[str, object]:
    """Trigger the billing sweep manually for a specific date."""
    sweep_date = date.fromisoformat(as_of) if as_of else None
    service = BillingSweepService(db, redis=redis)
    result = await service.execute_sweep(as_of=sweep_date)
    await db.commit()
    return result


# LS-EP-02: Overdue installment report
@router.get("/admin/finance/overdue-report", response_model=OverdueReportResponse)
async def get_overdue_report(
    as_of: str | None = Query(default=None),
    min_days_overdue: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    """LS-EP-02: Overdue installment report with outstanding amounts."""
    service = AccountingService(db, redis=redis)
    try:
        details = await service.get_ar_aging_details(as_of=as_of, min_days_overdue=min_days_overdue, limit=limit)
        total_outstanding = sum(d["outstanding_amount"] for d in details)
        from datetime import date as _date
        return {
            "as_of": as_of or _date.today().isoformat(),
            "total_count": len(details),
            "total_outstanding": total_outstanding,
            "items": details,
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# LS-EP-05: Tasdeeq / charity allocation report
@router.get("/admin/finance/tasdeeq-report", response_model=TasdeeqReportResponse)
async def get_tasdeeq_report(
    as_of: str | None = Query(default=None, description="Report date (YYYY-MM-DD). Defaults to today."),
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> dict[str, object]:
    """LS-EP-05: Generate TASDEEQ credit bureau report and return submission result."""
    from datetime import date as _date
    report_date = _date.fromisoformat(as_of) if as_of else None
    service = TasdeeqService(db)
    try:
        return await service.run_reporting_cycle(as_of_date=report_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# LS-CRIT-03: Charity auto-allocation disbursement
@router.post("/admin/finance/charity/process-allocation", response_model=CharityAutoAllocationResponse)
async def process_charity_allocation(
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: RequestContext = Depends(require_admin_role(["super_admin"])),
    __: bool = Depends(rate_limit_admin_writes),
) -> dict[str, object]:
    """LS-CRIT-03: Process pending charity allocations and auto-disburse if above nisab threshold."""
    service = CharityService(db, redis=redis)
    try:
        return await service.process_charity_allocation()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# LS-BL-07: Period close alerts
@router.get("/admin/finance/periods/upcoming-closes", response_model=list[PeriodCloseAlertResponse])
async def get_upcoming_period_closes(
    within_days: int = Query(default=7, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    _: RequestContext = Depends(require_admin_role(["finance_analyst", "super_admin"])),
) -> list[dict[str, object]]:
    """LS-BL-07: Returns open periods whose end_date is within `within_days` days — for alerting."""
    service = PeriodService(db)
    return await service.get_upcoming_period_closes(within_days=within_days)


# LS-EP-03: Internal billing sweep trigger (for Gateway)
@router.post("/internal/billing/trigger-sweep")
async def internal_trigger_billing_sweep(
    as_of: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    _: None = Depends(require_internal_request),
) -> dict[str, object]:
    """LS-EP-03: Internal endpoint allowing Gateway to trigger billing sweep manually."""
    from datetime import date as _date
    sweep_date = _date.fromisoformat(as_of) if as_of else None
    service = BillingSweepService(db, redis=redis)
    result = await service.execute_sweep(as_of=sweep_date)
    await db.commit()
    return result