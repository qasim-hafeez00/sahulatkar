from __future__ import annotations

import asyncio
import csv
import io
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.database import SessionLocal
from sk_shared.models.payment import Loan, Installment
from sk_shared.models.kyc import CustomerProfile
from sk_shared.models.auth import User


async def main() -> None:
    print({"status": "starting", "mode": "batch_csv", "task": "tasdeeq_report"})
    
    async with SessionLocal() as session:
        # Query active loans with user and profile data
        stmt = (
            select(Loan)
            .options(
                selectinload(Loan.installments)
            )
            .where(Loan.deleted_at.is_(None))
        )
        loans = (await session.execute(stmt)).scalars().all()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header (Targeting standard Credit Bureau fields)
        writer.writerow([
            "Loan ID", "User ID", "CNIC", "Principal", "Outstanding", 
            "Status", "Installments Paid", "Total Installments", "Last Payment Date"
        ])
        
        for loan in loans:
            # We need the CNIC from CustomerProfile
            profile_stmt = select(CustomerProfile).where(CustomerProfile.user_id == loan.user_id)
            profile = (await session.execute(profile_stmt)).scalar_one_or_none()
            cnic = profile.cnic if profile else "N/A"
            
            paid_count = sum(1 for i in loan.installments if i.status == "paid")
            last_payment = max((i.paid_at for i in loan.installments if i.paid_at), default=None)
            
            writer.writerow([
                loan.loan_number,
                loan.user_id,
                cnic,
                float(loan.principal_amount),
                float(loan.total_outstanding),
                loan.status,
                paid_count,
                loan.installment_count,
                last_payment.isoformat() if last_payment else "N/A"
            ])
            
        csv_content = output.getvalue()
        # In a real implementation, we would upload this to an SFTP server or TASDEEQ API
        print({"status": "completed", "records_processed": len(loans), "bytes": len(csv_content)})
        # For demo purposes, we'll log the first 100 characters
        # print(csv_content[:100])


if __name__ == "__main__":
    asyncio.run(main())