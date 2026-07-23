"use client"

import React, { motion } from "framer-motion"
import { useState, useEffect } from "react"
import { TrendingUp, TrendingDown, Info, CheckCircle, AlertCircle, XCircle, Brain, Activity } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"

interface CreditFactor {
  name: string
  value: number
  weight: number
  impact: 'positive' | 'negative' | 'neutral'
  description: string
}

interface CreditScoreData {
  score: number
  grade: string
  factors: CreditFactor[]
  recommendations: string[]
  creditLimit: string
  apr: string
  modelConfidence: number
  riskScore: number
  processingTime: number
}

interface UserProfile {
  age: number
  income: number
  employmentStatus: string
  creditHistory: number
  existingDebt: number
  assets: number
  cnicAge: number
  deviceScore: number
  behaviorScore: number
}

export function CreditScoringVisualization({ data }: { data: CreditScoreData }) {
  const [selectedFactor, setSelectedFactor] = useState<CreditFactor | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [modelMetrics, setModelMetrics] = useState({
    accuracy: 0.0,
    precision: 0.0,
    recall: 0.0,
    f1Score: 0.0
  })

  const getScoreColor = (score: number) => {
    if (score >= 750) return "text-green-600"
    if (score >= 700) return "text-blue-600"
    if (score >= 650) return "text-yellow-600"
    if (score >= 600) return "text-orange-600"
    return "text-red-600"
  }

  const getGradeColor = (grade: string) => {
    switch (grade) {
      case "A+": return "bg-green-100 text-green-800 border-green-200"
      case "A": return "bg-green-100 text-green-800 border-green-200"
      case "B": return "bg-blue-100 text-blue-800 border-blue-200"
      case "C": return "bg-yellow-100 text-yellow-800 border-yellow-200"
      case "D": return "bg-orange-100 text-orange-800 border-orange-200"
      default: return "bg-red-100 text-red-800 border-red-200"
    }
  }

  const getImpactIcon = (impact: string) => {
    switch (impact) {
      case "positive": return <TrendingUp className="w-4 h-4 text-green-600" />
      case "negative": return <TrendingDown className="w-4 h-4 text-red-600" />
      default: return <Info className="w-4 h-4 text-gray-600" />
    }
  }

  const getImpactColor = (impact: string) => {
    switch (impact) {
      case "positive": return "bg-green-50 border-green-200"
      case "negative": return "bg-red-50 border-red-200"
      default: return "bg-gray-50 border-gray-200"
    }
  }

  return (
    <div className="space-y-6">
      {/* Score Overview */}
      <Card className="border-0 shadow-large">
        <CardContent className="p-6">
          <div className="text-center mb-6">
            <h3 className="text-xl font-bold text-gray-900 mb-2">Your Credit Score</h3>
            <div className="flex items-center justify-center space-x-4">
              <div className={`text-5xl font-bold ${getScoreColor(data.score)}`}>
                {data.score}
              </div>
              <div className="text-left">
                <div className={`inline-block px-3 py-1 rounded-full text-sm font-medium border ${getGradeColor(data.grade)}`}>
                  Grade {data.grade}
                </div>
                <div className="mt-2 text-sm text-gray-600">
                  Credit Limit: <span className="font-semibold">{data.creditLimit}</span>
                </div>
                <div className="text-sm text-gray-600">
                  APR: <span className="font-semibold">{data.apr}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Score Meter */}
          <div className="relative mb-6">
            <div className="h-4 bg-gradient-to-r from-red-500 via-orange-500 and via-yellow-500 via-green-500 to-green-600 rounded-full" />
            <motion.div
              className="absolute top-1/2 transform -translate-y-1/2 w-6 h-6 bg-white border-2 border-gray-800 rounded-full shadow-lg"
              animate={{ left: `${(data.score / 850) * 100}%` }}
              style={{ left: `${(data.score / 850) * 100}%` }}
              transition={{ duration: 1, ease: "easeOut" }}
            />
            <div className="flex justify-between mt-2 text-xs text-gray-600">
              <span>300</span>
              <span>450</span>
              <span>600</span>
              <span>750</span>
              <span>850</span>
            </div>
          </div>

          {/* Credit Factors */}
          <div>
            <h4 className="font-semibold text-gray-900 mb-4">Credit Factors</h4>
            <div className="space-y-3">
              {data.factors.map((factor, index) => (
                <motion.div
                  key={factor.name}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.6, delay: index * 0.1 }}
                  className={`border rounded-xl p-4 cursor-pointer transition-all duration-200 ${getImpactColor(factor.impact)}`}
                  onClick={() => setSelectedFactor(factor === selectedFactor ? null : factor)}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-3">
                      {getImpactIcon(factor.impact)}
                      <span className="font-medium text-gray-900">{factor.name}</span>
                    </div>
                    <div className="text-right">
                      <div className="font-semibold text-gray-900">{factor.value}</div>
                      <div className="text-xs text-gray-600">Weight: {factor.weight}%</div>
                    </div>
                  </div>
                  
                  {/* Progress Bar */}
                  <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
                    <motion.div
                      className={`h-2 rounded-full ${
                        factor.impact === "positive" ? "bg-green-500" :
                        factor.impact === "negative" ? "bg-red-500" : "bg-gray-500"
                      }`}
                      initial={{ width: 0 }}
                      animate={{ width: `${factor.value}%` }}
                      transition={{ duration: 1, delay: index * 0.2 }}
                    />
                  </div>

                  {/* Expandable Details */}
                  {selectedFactor === factor && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-3 pt-3 border-t border-gray-200"
                    >
                      <p className="text-sm text-gray-600">{factor.description}</p>
                    </motion.div>
                  )}
                </motion.div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Recommendations */}
      <Card className="border-0 shadow-large">
        <CardContent className="p-6">
          <h3 className="text-xl font-bold text-gray-900 mb-4">Recommendations</h3>
          <div className="space-y-3">
            {data.recommendations.map((rec, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: index * 0.1 }}
                className="flex items-start space-x-3 p-3 bg-blue-50 rounded-lg"
              >
                <CheckCircle className="w-5 h-5 text-blue-600 mt-0.5" />
                <p className="text-sm text-blue-800">{rec}</p>
              </motion.div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// Sample data for demonstration
export const sampleCreditData: CreditScoreData = {
  score: 750,
  grade: "A+",
  modelConfidence: 0.94,
  riskScore: 0.12,
  processingTime: 0.8,
  factors: [
    {
      name: "Payment History",
      value: 95,
      weight: 35,
      impact: "positive",
      description: "Excellent payment history with no late payments or defaults."
    },
    {
      name: "Credit Utilization",
      value: 20,
      weight: 30,
      impact: "positive",
      description: "Low credit utilization shows responsible credit management."
    },
    {
      name: "Credit Age",
      value: 70,
      weight: 15,
      impact: "positive",
      description: "Good credit age with established credit history."
    },
    {
      name: "Account Mix",
      value: 60,
      weight: 10,
      impact: "neutral",
      description: "Good mix of credit types showing diverse credit experience."
    },
    {
      name: "Recent Inquiries",
      value: 40,
      weight: 10,
      impact: "negative",
      description: "Several recent credit inquiries may temporarily impact score."
    }
  ],
  recommendations: [
    "Continue making timely payments to maintain your excellent score",
    "Keep credit utilization below 30% for optimal scoring",
    "Avoid opening too many new credit accounts in a short period",
    "Monitor your credit report regularly for accuracy"
  ],
  creditLimit: "PKR 50,000",
  apr: "8.5%"
}
