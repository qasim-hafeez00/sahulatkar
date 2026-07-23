import { apiFetch, ApiError } from "@/lib/api-client"

export interface RegisterInitiatePayload {
  phone: string
  first_name: string
  last_name: string
  email?: string
  referral_code?: string
  password?: string
}

export interface RegisterInitiateResult {
  otp_token: string
  masked_phone: string
  dev_otp?: string
}

/**
 * Result of a login/verify-otp call. Unlike the gateway's own AuthResponse,
 * this carries no tokens — src/app/api/auth/login and .../verify-otp (Next.js
 * Route Handlers) consume the gateway's access_token/refresh_token and set
 * them as httpOnly cookies server-side, so the browser never sees them.
 */
export interface AuthSessionResult {
  status: "ok"
  user_id: number
  kyc_status: string
}

export interface CurrentUser {
  user_id: number
  uuid: string
  phone: string
  kyc_status: string
  credit_limit: number | null
  available_credit: number
  status: string
}

export interface ForgotPasswordResult {
  masked_phone: string
  reset_token: string
  dev_otp?: string
}

/** Normalizes a Pakistani mobile number to the +92XXXXXXXXXX format the gateway expects. */
export function toE164Pakistan(rawPhone: string): string {
  const digits = rawPhone.trim().replace(/[^\d]/g, "")
  if (digits.startsWith("92")) return `+${digits}`
  if (digits.startsWith("0")) return `+92${digits.slice(1)}`
  return `+92${digits}`
}

export const authApi = {
  registerInitiate(payload: RegisterInitiatePayload) {
    return apiFetch<RegisterInitiateResult>("/auth/register/initiate", {
      method: "POST",
      body: JSON.stringify(payload),
    })
  },

  async verifyOtp(otpToken: string, otpCode: string): Promise<AuthSessionResult> {
    const response = await fetch("/api/auth/verify-otp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ otp_token: otpToken, otp_code: otpCode }),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new ApiError(response.status, data.message ?? "Verification failed")
    }
    return data as AuthSessionResult
  },

  resendOtp(otpToken: string) {
    return apiFetch<RegisterInitiateResult>("/auth/otp/resend", {
      method: "POST",
      body: JSON.stringify({ otp_token: otpToken }),
    })
  },

  async login(phone: string, password: string): Promise<AuthSessionResult> {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone, password }),
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new ApiError(response.status, data.message ?? "Login failed")
    }
    return data as AuthSessionResult
  },

  me() {
    return apiFetch<CurrentUser>("/auth/me", { auth: true })
  },

  async logout() {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => {})
  },

  forgotPassword(phone: string) {
    return apiFetch<ForgotPasswordResult>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ phone }),
    })
  },

  resetPassword(resetToken: string, otpCode: string, newPassword: string) {
    return apiFetch<{ success: boolean }>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ reset_token: resetToken, otp_code: otpCode, new_password: newPassword }),
    })
  },
}
