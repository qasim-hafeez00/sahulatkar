import { apiFetch } from "@/lib/api-client"

export interface KycVerification {
  id: number
  status: "pending" | "submitted" | "in_review" | "approved" | "rejected"
  cnic_front_image_url: string | null
  cnic_back_image_url: string | null
  liveness_video_url: string | null
  rejection_reason: string | null
  attempt_number: number
  nadra_verified_at: string | null
  rejection_code: string | null
}

export interface CustomerProfile {
  id: number
  user_id: number
  first_name: string
  last_name: string
  cnic: string
  dob: string
  address: string | null
  created_at: string
  updated_at: string
}

export type KycDocumentType = "cnic_front" | "cnic_back" | "liveness_video"

export const kycApi = {
  start() {
    return apiFetch<KycVerification>("/kyc/start", { method: "POST", auth: true })
  },

  status() {
    return apiFetch<KycVerification>("/kyc/status", { auth: true })
  },

  async upload(documentType: KycDocumentType, file: Blob, filename: string) {
    const form = new FormData()
    form.append("file", file, filename)
    return apiFetch<KycVerification>(`/kyc/upload/${documentType}`, {
      method: "POST",
      auth: true,
      body: form,
    })
  },

  submit() {
    return apiFetch<KycVerification>("/kyc/submit", { method: "POST", auth: true })
  },

  saveProfile(payload: { first_name: string; last_name: string; cnic: string; dob: string; address?: string }) {
    return apiFetch<CustomerProfile>("/kyc/profile", {
      method: "PUT",
      auth: true,
      body: JSON.stringify(payload),
    })
  },

  getProfile() {
    return apiFetch<CustomerProfile>("/kyc/profile", { auth: true })
  },
}
