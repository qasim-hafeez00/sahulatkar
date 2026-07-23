"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Bell, CreditCard, Info, ShoppingBag, Truck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { notificationsApi, notificationTarget, type NotificationItem } from "@/lib/notifications-api"

function getIcon(category: string) {
  switch (category) {
    case "payment":
      return <CreditCard className="w-5 h-5" />
    case "delivery":
      return <Truck className="w-5 h-5" />
    case "credit":
      return <ShoppingBag className="w-5 h-5" />
    default:
      return <Info className="w-5 h-5" />
  }
}

function getColor(category: string) {
  switch (category) {
    case "payment":
      return "text-orange-600 bg-orange-100"
    case "delivery":
      return "text-blue-600 bg-blue-100"
    case "credit":
      return "text-emerald-600 bg-emerald-100"
    case "kyc":
      return "text-purple-600 bg-purple-100"
    default:
      return "text-gray-600 bg-gray-100"
  }
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

  if (!loaded) return null

  const unreadCount = notifications.filter((n) => !n.is_read).length

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="container mx-auto max-w-3xl px-4">
        <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.6 }} className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Notifications</h1>
            <p className="text-gray-600 dark:text-gray-400">Updates on your KYC, orders, payments, and financing</p>
          </div>
          {unreadCount > 0 && (
            <Button variant="outline" onClick={handleMarkAllRead}>
              Mark all as read
            </Button>
          )}
        </motion.div>

        <Card className="border-0 shadow-large">
          <CardContent className="p-0">
            {notifications.length === 0 ? (
              <div className="p-12 text-center">
                <Bell className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                <p className="text-gray-500">You have no notifications yet.</p>
              </div>
            ) : (
              <div className="divide-y divide-gray-100 dark:divide-white/5">
                {notifications.map((notification) => (
                  <button
                    key={notification.id}
                    onClick={() => handleOpen(notification)}
                    className={`w-full text-left p-5 flex items-start gap-4 transition-colors hover:bg-gray-50 dark:hover:bg-white/5 ${
                      !notification.is_read ? "bg-orange-50/40 dark:bg-orange-500/5" : ""
                    }`}
                  >
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${getColor(notification.category)}`}>
                      {getIcon(notification.category)}
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
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
