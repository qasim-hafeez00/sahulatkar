"use client"

import { motion } from "framer-motion"
import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { Bell, CreditCard, ShieldCheck, ShoppingBag, Truck, Info } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { notificationsApi, notificationTarget, type NotificationItem } from "@/lib/notifications-api"
import { getNotificationCategoryMeta, TONE_STYLES } from "@/lib/status"

const CATEGORY_ICON: Record<string, React.ElementType> = {
  payment: CreditCard,
  delivery: Truck,
  credit: ShoppingBag,
  kyc: ShieldCheck,
  general: Info,
}

function dayBucket(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const diffDays = Math.round((startOfDay(now) - startOfDay(date)) / (1000 * 60 * 60 * 24))
  if (diffDays <= 0) return "Today"
  if (diffDays === 1) return "Yesterday"
  if (diffDays < 7) return "This Week"
  return "Earlier"
}

function NotificationsSkeleton() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-3xl px-4 animate-pulse">
        <div className="card-surface h-10 w-56 rounded-xl mb-3" />
        <div className="card-surface h-5 w-72 rounded-lg mb-8" />
        <div className="card-surface h-96 rounded-2xl" />
      </div>
    </div>
  )
}

export default function NotificationsPage() {
  const router = useRouter()
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever renders.
    notificationsApi
      .list()
      .then((result) => setNotifications(result.items))
      .finally(() => setLoaded(true))
  }, [])

  const handleOpen = async (notification: NotificationItem) => {
    if (!notification.is_read) {
      try {
        await notificationsApi.markRead(notification.id)
        setNotifications((prev) => prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n)))
      } catch {
        // non-critical
      }
    }
    router.push(notificationTarget(notification))
  }

  const handleMarkAllRead = async () => {
    try {
      await notificationsApi.markAllRead()
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
    } catch {
      // non-critical
    }
  }

  const groups = useMemo(() => {
    const buckets = new Map<string, NotificationItem[]>()
    for (const n of notifications) {
      const key = dayBucket(n.created_at)
      if (!buckets.has(key)) buckets.set(key, [])
      buckets.get(key)!.push(n)
    }
    const order = ["Today", "Yesterday", "This Week", "Earlier"]
    return order.filter((key) => buckets.has(key)).map((key) => ({ key, items: buckets.get(key)! }))
  }, [notifications])

  if (!loaded) return <NotificationsSkeleton />

  const unreadCount = notifications.filter((n) => !n.is_read).length

  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-3xl px-4">
        <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.6 }} className="mb-8 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight mb-1.5">Notifications</h1>
            <p className="text-gray-600 dark:text-gray-400">Updates on your verification, orders, and payments</p>
          </div>
          {unreadCount > 0 && (
            <Button variant="outline" onClick={handleMarkAllRead} className="flex-none">
              Mark all as read
            </Button>
          )}
        </motion.div>

        {notifications.length === 0 ? (
          <Card className="card-surface">
            <CardContent className="p-12 text-center">
              <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 bg-orange-500/10">
                <Bell className="w-8 h-8 text-orange-500" />
              </div>
              <p className="text-gray-500">You&apos;re all caught up — nothing to show yet.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            {groups.map((group, groupIndex) => (
              <motion.div key={group.key} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: groupIndex * 0.08 }}>
                <h2 className="text-xs font-bold uppercase tracking-wide text-gray-500 mb-3">{group.key}</h2>
                <Card className="card-surface overflow-hidden">
                  <CardContent className="p-0">
                    <div className="divide-y divide-gray-100 dark:divide-white/5">
                      {group.items.map((notification) => {
                        const CatIcon = CATEGORY_ICON[notification.category] ?? Info
                        const tone = TONE_STYLES[getNotificationCategoryMeta(notification.category).tone]
                        return (
                          <button
                            key={notification.id}
                            onClick={() => handleOpen(notification)}
                            className={`w-full text-left p-5 flex items-start gap-4 transition-colors hover:bg-gray-50 dark:hover:bg-white/5 ${
                              !notification.is_read ? "bg-orange-50/40 dark:bg-orange-500/5" : ""
                            }`}
                          >
                            <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 border ${tone.badge}`}>
                              <CatIcon className="w-5 h-5" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className={`text-gray-900 dark:text-white ${!notification.is_read ? "font-semibold" : "font-medium"}`}>
                                {notification.title}
                              </p>
                              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{notification.body}</p>
                              <p className="text-xs text-gray-500 mt-2">{new Date(notification.created_at).toLocaleString()}</p>
                            </div>
                            {!notification.is_read && <span className="mt-1 h-2 w-2 rounded-full bg-orange-500 flex-shrink-0" />}
                          </button>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
