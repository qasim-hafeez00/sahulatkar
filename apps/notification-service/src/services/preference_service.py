from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sk_shared.models.notification import NotificationPreference

NON_OPTOUT_CATEGORIES = {"auth", "compliance"}

class PreferenceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def filter_channels(
        self, user_id: int, category: str, requested_channels: list[str]
    ) -> list[str]:
        if category in NON_OPTOUT_CATEGORIES:
            return requested_channels

        pref = await self.db.scalar(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.category == category,
            )
        )
        
        # Check for global unsubscribe (stored in any row or a special 'global' row)
        is_global_unsub = await self.db.scalar(
            select(NotificationPreference.is_globally_unsubscribed)
            .where(NotificationPreference.user_id == user_id)
            .where(NotificationPreference.is_globally_unsubscribed)
            .limit(1)
        )
        
        if is_global_unsub:
            return []

        if not pref:
            return requested_channels

        allowed = []
        if "sms" in requested_channels and pref.sms_enabled:
            allowed.append("sms")
        if "whatsapp" in requested_channels and pref.whatsapp_enabled:
            allowed.append("whatsapp")
        if "push" in requested_channels and pref.push_enabled:
            allowed.append("push")
        if "email" in requested_channels and pref.email_enabled:
            allowed.append("email")
            
        return allowed

    async def get_all_preferences(self, user_id: int) -> list[NotificationPreference]:
        return list((await self.db.scalars(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )).all())

    async def update_preferences(self, user_id: int, updates: list[dict]) -> list[NotificationPreference]:
        """Bulk update user preferences for multiple categories."""
        from sqlalchemy.dialects.postgresql import insert
        
        results = []
        for item in updates:
            category = item.get("category")
            if not category or category in NON_OPTOUT_CATEGORIES:
                continue
            
            # Extract only boolean fields
            update_data = {
                k: v for k, v in item.items() 
                if k in ("sms_enabled", "whatsapp_enabled", "push_enabled", "email_enabled")
            }
            
            stmt = insert(NotificationPreference).values(
                user_id=user_id,
                category=category,
                **update_data
            ).on_conflict_do_update(
                index_elements=["user_id", "category"],
                set_=update_data
            ).returning(NotificationPreference)
            
            res = await self.db.scalar(stmt)
            results.append(res)
            
        await self.db.commit()
        return results

    async def toggle_global_unsubscribe(self, user_id: int, unsubscribe: bool) -> None:
        """Set the global unsubscribe flag for all preference rows of the user."""
        from sqlalchemy.dialects.postgresql import insert
        from sqlalchemy import update
        
        # 1. Update existing rows
        res = await self.db.execute(
            update(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
            .values(is_globally_unsubscribed=unsubscribe)
        )
        
        # 2. If no rows updated, create a 'global' row to hold the flag
        if res.rowcount == 0:
            stmt = insert(NotificationPreference).values(
                user_id=user_id,
                category="global",
                is_globally_unsubscribed=unsubscribe
            ).on_conflict_do_update(
                index_elements=["user_id", "category"],
                set_={"is_globally_unsubscribed": unsubscribe}
            )
            await self.db.execute(stmt)
            
        await self.db.commit()
