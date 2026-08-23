"use client"

import { motion } from "framer-motion"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { AlertCircle, CheckCircle2, CreditCard, KeyRound, LifeBuoy, Lock, LogOut, User as UserIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { authApi, type CurrentUser } from "@/lib/auth-api"
import { kycApi, type CustomerProfile } from "@/lib/kyc-api"
import { humanizeAccountStatus, getKycStatusMeta, TONE_STYLES } from "@/lib/status"
import { useAuth } from "@/components/auth/auth-guard"

function ProfileSkeleton() {
  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-3xl px-4 animate-pulse">
        <div className="card-surface h-10 w-64 rounded-xl mb-3" />
        <div className="card-surface h-5 w-80 rounded-lg mb-8" />
        <div className="card-surface h-32 rounded-2xl mb-6" />
        <div className="card-surface h-72 rounded-2xl" />
      </div>
    </div>
  )
}

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

  if (!loaded) return <ProfileSkeleton />

  const displayName = profile ? `${profile.first_name} ${profile.last_name}` : "Your Account"
  const initials = profile ? `${profile.first_name[0] ?? ""}${profile.last_name[0] ?? ""}`.toUpperCase() : "SK"
  const kycMeta = getKycStatusMeta(currentUser?.kyc_status)
  const kycTone = TONE_STYLES[kycMeta.tone]
  const KycIcon = kycTone.icon
  const memberSince = profile
    ? new Date(profile.created_at).toLocaleDateString(undefined, { month: "long", year: "numeric" })
    : null

  return (
    <div className="min-h-screen pt-28 pb-16 page-canvas">
      <div className="container mx-auto max-w-3xl px-4">
        <motion.div initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ duration: 0.6 }} className="mb-8">
          <h1 className="text-3xl font-extrabold text-gray-900 dark:text-white tracking-tight mb-1.5">Account Settings</h1>
          <p className="text-gray-600 dark:text-gray-400">Manage your profile, security, and preferences</p>
        </motion.div>

        {/* Identity header */}
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }}>
          <Card className="card-surface mb-6">
            <CardContent className="p-6 flex flex-col sm:flex-row sm:items-center gap-4 sm:justify-between">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center text-white font-extrabold text-lg flex-none shadow-lg shadow-orange-500/10">
                  {initials}
                </div>
                <div>
                  <h2 className="font-extrabold text-gray-900 dark:text-white text-lg">{displayName}</h2>
                  <p className="text-sm text-gray-500">{currentUser?.phone ?? "—"}</p>
                  {memberSince && <p className="text-xs text-gray-400 mt-0.5">Member since {memberSince}</p>}
                </div>
              </div>
              <div className="flex flex-col items-start sm:items-end gap-1.5">
                <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${kycTone.badge}`}>
                  <KycIcon className="w-3.5 h-3.5" />
                  Identity {kycMeta.label}
                </span>
                <span className="text-xs text-gray-400">Account: {humanizeAccountStatus(currentUser?.status)}</span>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.15 }}>
          <Card className="card-surface mb-6">
            <CardContent className="p-6">
              <div className="flex items-center gap-2 mb-6">
                <UserIcon className="w-5 h-5 text-orange-500" />
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">Personal Information</h2>
              </div>

              <div className="mb-4">
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Mobile Number</label>
                <Input value={currentUser?.phone ?? ""} disabled className="w-full h-12 rounded-xl bg-gray-50 dark:bg-white/5 text-gray-500" />
              </div>

              {!profile ? (
                <p className="text-sm text-gray-500">Complete identity verification to add your name, CNIC, and address.</p>
              ) : (
                <form onSubmit={handleSave} className="space-y-4">
                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">First Name</label>
                      <Input value={firstName} onChange={(e) => setFirstName(e.target.value)} className="w-full h-12 rounded-xl" required />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Last Name</label>
                      <Input value={lastName} onChange={(e) => setLastName(e.target.value)} className="w-full h-12 rounded-xl" required />
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">CNIC (verified)</label>
                    <Input value={profile.cnic} disabled className="w-full h-12 rounded-xl bg-gray-50 dark:bg-white/5 text-gray-500 font-mono" />
                  </div>

                  <div>
                    <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Address</label>
                    <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Your delivery / correspondence address" className="w-full h-12 rounded-xl" />
                  </div>

                  {error && (
                    <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                      <AlertCircle className="w-4 h-4 flex-none" /> {error}
                    </div>
                  )}
                  {success && (
                    <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="w-4 h-4 flex-none" /> {success}
                    </div>
                  )}

                  <Button
                    type="submit"
                    disabled={isSaving}
                    className="h-12 rounded-xl font-bold px-6 bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 shadow-lg shadow-orange-500/10 btn-smooth disabled:opacity-50"
                  >
                    {isSaving ? "Saving…" : "Save Changes"}
                  </Button>
                </form>
              )}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }}>
          <Card className="card-surface mb-6">
            <CardContent className="p-6">
              <div className="flex items-center gap-2 mb-4">
                <Lock className="w-5 h-5 text-orange-500" />
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">Security</h2>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 leading-relaxed">
                Your identity documents are encrypted and can only be accessed during identity verification — never shared or sold.
              </p>
              <Button
                variant="outline"
                onClick={() => router.push("/auth/forgot-password")}
                className="h-11 rounded-xl font-semibold flex items-center gap-2"
              >
                <KeyRound className="w-4 h-4" />
                Change Password
              </Button>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.25 }} className="grid sm:grid-cols-3 gap-4">
          <button onClick={() => router.push("/payment-methods")} className="card-surface p-5 flex items-center gap-3 text-left">
            <CreditCard className="w-5 h-5 text-orange-500 flex-none" />
            <span className="font-semibold text-sm text-gray-900 dark:text-white">Payment Methods</span>
          </button>
          <button onClick={() => router.push("/support")} className="card-surface p-5 flex items-center gap-3 text-left">
            <LifeBuoy className="w-5 h-5 text-orange-500 flex-none" />
            <span className="font-semibold text-sm text-gray-900 dark:text-white">Help &amp; Support</span>
          </button>
          <button onClick={() => logout()} className="card-surface p-5 flex items-center gap-3 text-left hover:border-red-500/30">
            <LogOut className="w-5 h-5 text-red-500 flex-none" />
            <span className="font-semibold text-sm text-gray-900 dark:text-white">Log Out</span>
          </button>
        </motion.div>
      </div>
    </div>
  )
}
