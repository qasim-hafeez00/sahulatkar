"use client"

import { motion, AnimatePresence } from "framer-motion"
import { useState, useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Bell, CreditCard, Info, ShoppingBag, Truck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { notificationsApi, notificationTarget, type NotificationItem } from "@/lib/notifications-api"

function getNotificationIcon(category: string) {
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

function getNotificationColor(category: string) {
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
              className="absolute right-0 mt-2 w-80 bg-white dark:bg-slate-900 rounded-xl shadow-2xl border border-gray-200 dark:border-white/10 z-50 max-h-96 overflow-hidden"
            >
              <div className="p-4 border-b border-gray-200 dark:border-white/10">
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-gray-900 dark:text-white">Notifications</h3>
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
                    <Bell className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                    <p className="text-gray-500">No notifications</p>
                  </div>
                ) : (
                  <div className="divide-y divide-gray-100 dark:divide-white/5">
                    {notifications.map((notification) => (
                      <div
                        key={notification.id}
                        className={`p-4 hover:bg-gray-50 dark:hover:bg-white/5 cursor-pointer transition-colors ${
                          !notification.is_read ? "bg-blue-50 dark:bg-blue-500/5" : ""
                        }`}
                        onClick={() => handleOpenNotification(notification)}
                      >
                        <div className="flex items-start space-x-3">
                          <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${getNotificationColor(notification.category)}`}>
                            {getNotificationIcon(notification.category)}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className={`text-sm text-gray-900 dark:text-white ${!notification.is_read ? "font-semibold" : "font-medium"}`}>
                              {notification.title}
                            </p>
                            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">{notification.body}</p>
                            <p className="text-xs text-gray-500 mt-2">{formatTimestamp(notification.created_at)}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="p-3 border-t border-gray-200 dark:border-white/10">
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
