"use client"

import { motion, AnimatePresence } from "framer-motion"
import { useState, useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Bell, CreditCard, ShieldCheck, ShoppingBag, Truck, Info } from "lucide-react"
import { Button } from "@/components/ui/button"
import { notificationsApi, notificationTarget, type NotificationItem } from "@/lib/notifications-api"
import { getNotificationCategoryMeta, TONE_STYLES } from "@/lib/status"

const CATEGORY_ICON: Record<string, React.ElementType> = {
  payment: CreditCard,
  delivery: Truck,
  credit: ShoppingBag,
  kyc: ShieldCheck,
  general: Info,
}

function formatTimestamp(iso: string) {
  const date = new Date(iso)
  const diff = Date.now() - date.getTime()
  const hours = Math.floor(diff / (1000 * 60 * 60))
  const days = Math.floor(hours / 24)
  if (days > 0) return `${days} day${days > 1 ? "s" : ""} ago`
  if (hours > 0) return `${hours} hour${hours > 1 ? "s" : ""} ago`
  return "Just now"
}

export function NotificationSystem() {
  const router = useRouter()
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [isOpen, setIsOpen] = useState(false)

  const load = useCallback(() => {
    notificationsApi
      .list()
      .then((result) => {
        setNotifications(result.items)
        setUnreadCount(result.unread_count)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [load])

  const handleOpenNotification = async (notification: NotificationItem) => {
    if (!notification.is_read) {
      try {
        await notificationsApi.markRead(notification.id)
        setNotifications((prev) => prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n)))
        setUnreadCount((prev) => Math.max(prev - 1, 0))
      } catch {
        // non-critical
      }
    }
    setIsOpen(false)
    router.push(notificationTarget(notification))
  }

  const handleMarkAllRead = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await notificationsApi.markAllRead()
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
      setUnreadCount(0)
    } catch {
      // non-critical
    }
  }

  return (
    <div className="relative">
      <Button variant="ghost" onClick={() => setIsOpen(!isOpen)} className="relative" aria-label="Notifications">
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center"
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </motion.span>
        )}
      </Button>

      <AnimatePresence>
        {isOpen && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              className="absolute right-0 mt-2 w-80 card-surface z-50 max-h-96 overflow-hidden"
            >
              <div className="p-4 border-b border-gray-100 dark:border-white/10">
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-gray-900 dark:text-white text-sm">Notifications</h3>
                  {unreadCount > 0 && (
                    <Button variant="ghost" size="sm" onClick={handleMarkAllRead} className="text-xs">
                      Mark all as read
                    </Button>
                  )}
                </div>
              </div>

              <div className="overflow-y-auto max-h-72">
                {notifications.length === 0 ? (
                  <div className="p-8 text-center">
                    <Bell className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                    <p className="text-sm text-gray-500">No notifications</p>
                  </div>
                ) : (
                  <div className="divide-y divide-gray-100 dark:divide-white/5">
                    {notifications.slice(0, 8).map((notification) => {
                      const CatIcon = CATEGORY_ICON[notification.category] ?? Info
                      const tone = TONE_STYLES[getNotificationCategoryMeta(notification.category).tone]
                      return (
                        <div
                          key={notification.id}
                          className={`p-4 hover:bg-gray-50 dark:hover:bg-white/5 cursor-pointer transition-colors ${
                            !notification.is_read ? "bg-orange-50/40 dark:bg-orange-500/5" : ""
                          }`}
                          onClick={() => handleOpenNotification(notification)}
                        >
                          <div className="flex items-start gap-3">
                            <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 border ${tone.badge}`}>
                              <CatIcon className="w-4 h-4" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className={`text-sm text-gray-900 dark:text-white ${!notification.is_read ? "font-semibold" : "font-medium"}`}>
                                {notification.title}
                              </p>
                              <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5 line-clamp-2">{notification.body}</p>
                              <p className="text-xs text-gray-500 mt-1.5">{formatTimestamp(notification.created_at)}</p>
                            </div>
                            {!notification.is_read && <span className="mt-1.5 h-2 w-2 rounded-full bg-orange-500 flex-shrink-0" />}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              <div className="p-3 border-t border-gray-100 dark:border-white/10">
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full text-xs"
                  onClick={() => {
                    setIsOpen(false)
                    router.push("/notifications")
                  }}
                >
                  View all notifications
                </Button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}
