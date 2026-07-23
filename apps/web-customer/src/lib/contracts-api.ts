import { apiFetch } from "@/lib/api-client"

export interface WakalahGenerateResult {
  contract_id: number
  contract_number: string
  principal_name: string
  agent_name: string
  authorized_amount: number
  valid_until: string
  otp_sent: boolean
  dev_otp?: string
}

export interface ContractDisclosure {
  cost_price: number
  profit_amount: number
  total_sale_price: number
  profit_rate_pct: number
  currency: string
  installment_count: number
}

export interface MurabahaGenerateResult {
  contract_id: number
  contract_number: string
  disclosure: ContractDisclosure
  otp_sent: boolean
  dev_otp?: string
}

export interface ContractSignResult {
  signed: boolean
  signed_at: string
  order_status: string
}

export const contractsApi = {
  generateWakalah(orderId: number) {
    return apiFetch<WakalahGenerateResult>("/contracts/wakalah/generate", {
      method: "POST",
      auth: true,
      body: JSON.stringify({ order_id: orderId }),
    })
  },

  signWakalah(contractId: number, otpCode: string) {
    return apiFetch<ContractSignResult>("/contracts/wakalah/sign", {
      method: "POST",
      auth: true,
      body: JSON.stringify({ contract_id: contractId, otp_code: otpCode }),
    })
  },

  generateMurabaha(orderId: number, installmentCount: 3 | 4 | 6 | 12) {
    return apiFetch<MurabahaGenerateResult>("/contracts/murabaha/generate", {
      method: "POST",
      auth: true,
      body: JSON.stringify({ order_id: orderId, installment_count: installmentCount }),
    })
  },

  signMurabaha(contractId: number, otpCode: string) {
    return apiFetch<ContractSignResult>("/contracts/murabaha/sign", {
      method: "POST",
      auth: true,
      body: JSON.stringify({
        contract_id: contractId,
        otp_code: otpCode,
        confirmation_checkbox: true,
      }),
    })
  },
}
