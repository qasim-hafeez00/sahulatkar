"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { AlertCircle, CheckCircle2, CreditCard, LifeBuoy, LogOut, Shield, User as UserIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { authApi, type CurrentUser } from "@/lib/auth-api"
import { kycApi, type CustomerProfile } from "@/lib/kyc-api"
import { formatCurrency } from "@/lib/utils"
import { useAuth } from "@/components/auth/auth-guard"

export default function ProfilePage() {
  const router = useRouter()
  const { logout } = useAuth()
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [profile, setProfile] = useState<CustomerProfile | null>(null)
  const [firstName, setFirstName] = useState("")
  const [lastName, setLastName] = useState("")
  const [address, setAddress] = useState("")
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [isSaving, setIsSaving] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    // Auth is enforced server-side by middleware.ts before this page ever renders.
    Promise.all([authApi.me(), kycApi.getProfile().catch(() => null)]).then(([user, prof]) => {
      setCurrentUser(user)
      if (prof) {
        setProfile(prof)
        setFirstName(prof.first_name)
        setLastName(prof.last_name)
        setAddress(prof.address ?? "")
      }
    }).finally(() => setLoaded(true))
  }, [router])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!profile) return
    setError("")
    setSuccess("")
    setIsSaving(true)
    try {
      const updated = await kycApi.saveProfile({
        first_name: firstName,
        last_name: lastName,
        cnic: profile.cnic,
        dob: profile.dob,
        address: address || undefined,
      })
      setProfile(updated)
      setSuccess("Profile updated successfully.")
    } catch {
      setError("Could not update your profile. Please try again.")
    } finally {
      setIsSaving(false)
    }
  }

  if (!loaded) return null

  return (
    <div className="min-h-screen pt-28 pb-16">
      <div className="container mx-auto max-w-3xl px-4">
        <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.6 }} className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Account Settings</h1>
          <p className="text-gray-600 dark:text-gray-400">Manage your profile, security, and account preferences</p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-6 mb-6">
          <Card className="border-0 shadow-sm">
            <CardContent className="p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Credit Limit</p>
              <p className="text-lg font-bold text-gray-900 dark:text-white">{formatCurrency(currentUser?.credit_limit ?? 0)}</p>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-sm">
            <CardContent className="p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Available Credit</p>
              <p className="text-lg font-bold text-emerald-600">{formatCurrency(currentUser?.available_credit ?? 0)}</p>
            </CardContent>
          </Card>
          <Card className="border-0 shadow-sm">
            <CardContent className="p-5">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Account Status</p>
              <p className="text-lg font-bold text-gray-900 dark:text-white capitalize">{currentUser?.status ?? "—"}</p>
            </CardContent>
          </Card>
        </div>

        <Card className="border-0 shadow-large mb-6">
          <CardContent className="p-6">
            <div className="flex items-center gap-2 mb-6">
              <UserIcon className="w-5 h-5 text-orange-500" />
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">Personal Information</h2>
            </div>

            <div className="mb-4">
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Mobile Number</label>
              <Input value={currentUser?.phone ?? ""} disabled className="w-full rounded-xl border border-gray-200 bg-gray-50 dark:bg-white/5 dark:border-white/10 py-3 px-4 text-gray-500" />
            </div>

            {!profile ? (
              <p className="text-sm text-gray-500">Complete KYC verification to add your name, CNIC, and address.</p>
            ) : (
              <form onSubmit={handleSave} className="space-y-4">
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">First Name</label>
                    <Input value={firstName} onChange={(e) => setFirstName(e.target.value)} className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4" required />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Last Name</label>
                    <Input value={lastName} onChange={(e) => setLastName(e.target.value)} className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4" required />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">CNIC (verified)</label>
                  <Input value={profile.cnic} disabled className="w-full rounded-xl border border-gray-200 bg-gray-50 dark:bg-white/5 dark:border-white/10 py-3 px-4 text-gray-500 font-mono" />
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Address</label>
                  <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Your delivery / correspondence address" className="w-full rounded-xl border border-gray-300 dark:border-white/10 bg-white dark:bg-white/5 py-3 px-4" />
                </div>

                {error && (
                  <div className="flex items-center gap-2 text-sm text-red-600">
                    <AlertCircle className="w-4 h-4" /> {error}
                  </div>
                )}
                {success && (
                  <div className="flex items-center gap-2 text-sm text-emerald-600">
                    <CheckCircle2 className="w-4 h-4" /> {success}
                  </div>
                )}

                <Button type="submit" disabled={isSaving} className="bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 disabled:opacity-60">
                  {isSaving ? "Saving..." : "Save Changes"}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        <div className="grid sm:grid-cols-3 gap-4">
          <button onClick={() => router.push("/payment-methods")} className="p-5 rounded-2xl border border-gray-200 dark:border-white/10 hover:border-orange-500/30 transition-colors flex items-center gap-3 text-left">
            <CreditCard className="w-5 h-5 text-orange-500" />
            <span className="font-semibold text-sm text-gray-900 dark:text-white">Payment Methods</span>
          </button>
          <button onClick={() => router.push("/support")} className="p-5 rounded-2xl border border-gray-200 dark:border-white/10 hover:border-orange-500/30 transition-colors flex items-center gap-3 text-left">
            <LifeBuoy className="w-5 h-5 text-orange-500" />
            <span className="font-semibold text-sm text-gray-900 dark:text-white">Help & Support</span>
          </button>
          <button onClick={() => logout()} className="p-5 rounded-2xl border border-gray-200 dark:border-white/10 hover:border-red-500/30 transition-colors flex items-center gap-3 text-left">
            <LogOut className="w-5 h-5 text-red-500" />
            <span className="font-semibold text-sm text-gray-900 dark:text-white">Log Out</span>
          </button>
        </div>

        <div className="mt-6 flex items-center gap-2 text-xs text-gray-500">
          <Shield className="w-4 h-4 text-orange-500" /> Your data is encrypted with AES-256 and your CNIC is stored using KMS encryption.
        </div>
      </div>
    </div>
  )
}
