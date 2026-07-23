"use client"

import React, { useState, useEffect } from "react"
import { motion } from "framer-motion"
import { Shield, Ban, AlertTriangle, CheckCircle, XCircle, Search, Filter, Eye, Settings, Database, TrendingUp, Users, CreditCard } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"

interface Merchant {
  id: string
  name: string
  category: string
  mcc: string
  status: 'approved' | 'restricted' | 'blacklisted' | 'pending'
  riskScore: number
  monthlyVolume: number
  transactionCount: number
  complaintRate: number
  lastChecked: string
  restrictions: string[]
  complianceIssues: string[]
}

interface MCCCategory {
  code: string
  description: string
  status: 'allowed' | 'restricted' | 'blocked'
  riskLevel: 'low' | 'medium' | 'high'
  monthlyLimit: number
  details: string
}

export function MerchantComplianceSystem() {
  const [merchants, setMerchants] = useState<Merchant[]>([])
  const [mccCategories, setMccCategories] = useState<MCCCategory[]>([])
  const [searchTerm, setSearchTerm] = useState("")
  const [selectedCategory, setSelectedCategory] = useState("all")
  const [isScanning, setIsScanning] = useState(false)
  const [scanResults, setScanResults] = useState<any[]>([])
  const [showDetails, setShowDetails] = useState<string | null>(null)

  useEffect(() => {
    // Initialize data
    setMerchants(getInitialMerchants())
    setMccCategories(getInitialMCCCategories())
  }, [])

  const getInitialMerchants = (): Merchant[] => [
    {
      id: "merchant-001",
      name: "Daraz Pakistan",
      category: "E-commerce",
      mcc: "5965",
      status: "approved",
      riskScore: 0.15,
      monthlyVolume: 25000000,
      transactionCount: 15420,
      complaintRate: 0.02,
      lastChecked: new Date().toISOString(),
      restrictions: [],
      complianceIssues: []
    },
    {
      id: "merchant-002",
      name: "TechWorld Electronics",
      category: "Electronics",
      mcc: "5732",
      status: "restricted",
      riskScore: 0.35,
      monthlyVolume: 8500000,
      transactionCount: 3420,
      complaintRate: 0.08,
      lastChecked: new Date().toISOString(),
      restrictions: ["Monthly limit: PKR 10M", "Enhanced monitoring required"],
      complianceIssues: ["High chargeback rate", "Delayed shipping reports"]
    },
    {
      id: "merchant-003",
      name: "QuickCash Services",
      category: "Financial Services",
      mcc: "6051",
      status: "blacklisted",
      riskScore: 0.85,
      monthlyVolume: 12000000,
      transactionCount: 890,
      complaintRate: 0.25,
      lastChecked: new Date().toISOString(),
      restrictions: ["All transactions blocked"],
      complianceIssues: ["Suspicious transaction patterns", "Regulatory violations", "High fraud indicators"]
    },
    {
      id: "merchant-004",
      name: "FoodPanda Pakistan",
      category: "Food Delivery",
      mcc: "5814",
      status: "approved",
      riskScore: 0.12,
      monthlyVolume: 18000000,
      transactionCount: 45600,
      complaintRate: 0.01,
      lastChecked: new Date().toISOString(),
      restrictions: [],
      complianceIssues: []
    }
  ]

  const getInitialMCCCategories = (): MCCCategory[] => [
    {
      code: "5965",
      description: "E-commerce - Non-store retailers",
      status: "allowed",
      riskLevel: "low",
      monthlyLimit: 50000000,
      details: "Online retail stores and marketplaces"
    },
    {
      code: "5732",
      description: "Electronics Stores",
      status: "restricted",
      riskLevel: "medium",
      monthlyLimit: 10000000,
      details: "Electronic equipment and appliance stores"
    },
    {
      code: "6051",
      description: "Financial Services",
      status: "blocked",
      riskLevel: "high",
      monthlyLimit: 0,
      details: "Financial institutions and money services"
    },
    {
      code: "5814",
      description: "Food Delivery",
      status: "allowed",
      riskLevel: "low",
      monthlyLimit: 30000000,
      details: "Fast food restaurants and delivery services"
    },
    {
      code: "7299",
      description: "Personal Services",
      status: "restricted",
      riskLevel: "medium",
      monthlyLimit: 5000000,
      details: "Personal care and grooming services"
    },
    {
      code: "7832",
      description: "Movie Theaters",
      status: "allowed",
      riskLevel: "low",
      monthlyLimit: 15000000,
      details: "Cinemas and entertainment venues"
    }
  ]

  const scanMerchantCompliance = async () => {
    setIsScanning(true)
    
    // Simulate compliance scanning
    setTimeout(() => {
      const results = merchants.map(merchant => ({
        merchantId: merchant.id,
        merchantName: merchant.name,
        scanTimestamp: new Date().toISOString(),
        complianceScore: Math.max(0, 1 - merchant.riskScore),
        issues: merchant.complianceIssues,
        recommendations: generateRecommendations(merchant),
        automatedActions: generateAutomatedActions(merchant)
      }))
      
      setScanResults(results)
      setIsScanning(false)
    }, 3000)
  }

  const generateRecommendations = (merchant: Merchant): string[] => {
    const recommendations = []
    
    if (merchant.riskScore > 0.7) {
      recommendations.push("Consider blacklisting due to high risk score")
    } else if (merchant.riskScore > 0.4) {
      recommendations.push("Implement enhanced monitoring")
      recommendations.push("Reduce transaction limits")
    }
    
    if (merchant.complaintRate > 0.1) {
      recommendations.push("Investigate customer complaints")
      recommendations.push("Require compliance improvement plan")
    }
    
    if (merchant.monthlyVolume > 20000000 && merchant.status !== 'approved') {
      recommendations.push("Conduct manual review for high volume merchant")
    }
    
    return recommendations
  }

  const generateAutomatedActions = (merchant: Merchant): string[] => {
    const actions = []
    
    if (merchant.riskScore > 0.8) {
      actions.push("AUTO_BLOCK: Transactions suspended")
      actions.push("ALERT: High-risk merchant detected")
    } else if (merchant.riskScore > 0.5) {
      actions.push("MONITOR: Enhanced transaction monitoring")
      actions.push("LIMIT: Daily transaction limits applied")
    }
    
    if (merchant.complaintRate > 0.15) {
      actions.push("REVIEW: Manual compliance review triggered")
    }
    
    return actions
  }

  const updateMerchantStatus = (merchantId: string, newStatus: Merchant['status']) => {
    setMerchants(prev => prev.map(merchant => {
      if (merchant.id === merchantId) {
        return {
          ...merchant,
          status: newStatus,
          riskScore: newStatus === 'blacklisted' ? 0.9 : 
                     newStatus === 'restricted' ? Math.max(0.4, merchant.riskScore) :
                     newStatus === 'approved' ? Math.min(0.2, merchant.riskScore) :
                     merchant.riskScore
        }
      }
      return merchant
    }))
  }

  const filteredMerchants = merchants.filter(merchant => {
    const matchesSearch = merchant.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         merchant.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         merchant.mcc.includes(searchTerm)
    
    const matchesCategory = selectedCategory === "all" || merchant.status === selectedCategory
    
    return matchesSearch && matchesCategory
  })

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'approved': return 'text-green-600 bg-green-100 border-green-200'
      case 'restricted': return 'text-orange-600 bg-orange-100 border-orange-200'
      case 'blacklisted': return 'text-red-600 bg-red-100 border-red-200'
      case 'pending': return 'text-blue-600 bg-blue-100 border-blue-200'
      default: return 'text-gray-600 bg-gray-100 border-gray-200'
    }
  }

  const getRiskColor = (score: number) => {
    if (score < 0.2) return 'text-green-600'
    if (score < 0.5) return 'text-orange-600'
    return 'text-red-600'
  }

  const getMCCStatusColor = (status: string) => {
    switch (status) {
      case 'allowed': return 'text-green-600 bg-green-100'
      case 'restricted': return 'text-orange-600 bg-orange-100'
      case 'blocked': return 'text-red-600 bg-red-100'
      default: return 'text-gray-600 bg-gray-100'
    }
  }

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Button onClick={scanMerchantCompliance} disabled={isScanning}>
            <Shield className="w-4 h-4 mr-2" />
            {isScanning ? 'Scanning...' : 'Scan Compliance'}
          </Button>
          <Button variant="outline">
            <Database className="w-4 h-4 mr-2" />
            Update Rules
          </Button>
        </div>
        
        <div className="flex items-center space-x-4">
          <Input
            placeholder="Search merchants..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-64"
            leftIcon={<Search className="w-4 h-4" />}
          />
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500"
          >
            <option value="all">All Status</option>
            <option value="approved">Approved</option>
            <option value="restricted">Restricted</option>
            <option value="blacklisted">Blacklisted</option>
            <option value="pending">Pending</option>
          </select>
        </div>
      </div>

      {/* Scan Results */}
      {scanResults.length > 0 && (
        <Card className="border-0 shadow-medium">
          <CardContent className="p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Compliance Scan Results</h3>
            <div className="space-y-3">
              {scanResults.map((result, index) => (
                <div key={index} className="p-4 bg-gray-50 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-gray-900">{result.merchantName}</span>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      result.complianceScore > 0.8 ? 'bg-green-100 text-green-800' :
                      result.complianceScore > 0.5 ? 'bg-orange-100 text-orange-800' :
                      'bg-red-100 text-red-800'
                    }`}>
                      Score: {Math.round(result.complianceScore * 100)}%
                    </span>
                  </div>
                  
                  {result.recommendations.length > 0 && (
                    <div className="mb-2">
                      <p className="text-sm font-medium text-gray-700 mb-1">Recommendations:</p>
                      <ul className="text-sm text-gray-600 space-y-1">
                        {result.recommendations.map((rec: string, i: number) => (
                          <li key={i} className="flex items-center space-x-2">
                            <AlertTriangle className="w-3 h-3 text-orange-500" />
                            <span>{rec}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {result.automatedActions.length > 0 && (
                    <div>
                      <p className="text-sm font-medium text-gray-700 mb-1">Automated Actions:</p>
                      <ul className="text-sm text-gray-600 space-y-1">
                        {result.automatedActions.map((action: string, i: number) => (
                          <li key={i} className="flex items-center space-x-2">
                            <Settings className="w-3 h-3 text-blue-500" />
                            <span>{action}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* MCC Categories */}
      <Card className="border-0 shadow-medium">
        <CardContent className="p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">MCC Category Restrictions</h3>
          <div className="grid gap-4">
            {mccCategories.map((category) => (
              <div key={category.code} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-1">
                    <span className="font-mono text-sm font-medium text-gray-900">{category.code}</span>
                    <span className="font-medium text-gray-900">{category.description}</span>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getMCCStatusColor(category.status)}`}>
                      {category.status.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600">{category.description}</p>
                  <div className="flex items-center space-x-4 mt-2 text-sm text-gray-500">
                    <span>Risk: {category.riskLevel}</span>
                    <span>Monthly Limit: PKR {category.monthlyLimit.toLocaleString()}</span>
                  </div>
                </div>
                
                <div className="flex items-center space-x-2">
                  <Button size="sm" variant="outline">
                    <Settings className="w-3 h-3" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Merchants List */}
      <div className="grid gap-4">
        {filteredMerchants.map((merchant) => (
          <Card key={merchant.id} className="border-0 shadow-medium">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-4">
                  <div className={`w-3 h-3 rounded-full ${
                    merchant.status === 'approved' ? 'bg-green-500' :
                    merchant.status === 'restricted' ? 'bg-orange-500' :
                    merchant.status === 'blacklisted' ? 'bg-red-500' : 'bg-blue-500'
                  }`} />
                  <div>
                    <h3 className="font-semibold text-gray-900">{merchant.name}</h3>
                    <p className="text-sm text-gray-600">{merchant.category} • MCC: {merchant.mcc}</p>
                  </div>
                </div>
                
                <div className="flex items-center space-x-3">
                  <span className={`px-3 py-1 rounded-full text-sm font-medium border ${getStatusColor(merchant.status)}`}>
                    {merchant.status.toUpperCase()}
                  </span>
                  <span className={`text-sm font-medium ${getRiskColor(merchant.riskScore)}`}>
                    Risk: {Math.round(merchant.riskScore * 100)}%
                  </span>
                  <div className="flex items-center space-x-1">
                    <Button 
                      size="sm" 
                      variant="outline"
                      onClick={() => setShowDetails(showDetails === merchant.id ? null : merchant.id)}
                    >
                      <Eye className="w-3 h-3" />
                    </Button>
                    <select
                      value={merchant.status}
                      onChange={(e) => updateMerchantStatus(merchant.id, e.target.value as Merchant['status'])}
                      className="text-sm px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-orange-500"
                    >
                      <option value="approved">Approve</option>
                      <option value="restricted">Restrict</option>
                      <option value="blacklisted">Blacklist</option>
                      <option value="pending">Pending</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Merchant Metrics */}
              <div className="grid grid-cols-4 gap-4 mb-4">
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <CreditCard className="w-5 h-5 text-gray-500 mx-auto mb-1" />
                  <p className="text-xs text-gray-600">Monthly Volume</p>
                  <p className="text-sm font-semibold text-gray-900">PKR {(merchant.monthlyVolume / 1000000).toFixed(1)}M</p>
                </div>
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <TrendingUp className="w-5 h-5 text-gray-500 mx-auto mb-1" />
                  <p className="text-xs text-gray-600">Transactions</p>
                  <p className="text-sm font-semibold text-gray-900">{merchant.transactionCount.toLocaleString()}</p>
                </div>
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <Users className="w-5 h-5 text-gray-500 mx-auto mb-1" />
                  <p className="text-xs text-gray-600">Complaint Rate</p>
                  <p className="text-sm font-semibold text-gray-900">{(merchant.complaintRate * 100).toFixed(1)}%</p>
                </div>
                <div className="text-center p-3 bg-gray-50 rounded-lg">
                  <AlertTriangle className="w-5 h-5 text-gray-500 mx-auto mb-1" />
                  <p className="text-xs text-gray-600">Risk Score</p>
                  <p className={`text-sm font-semibold ${getRiskColor(merchant.riskScore)}`}>
                    {Math.round(merchant.riskScore * 100)}%
                  </p>
                </div>
              </div>

              {/* Detailed Information */}
              {showDetails === merchant.id && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="pt-4 border-t border-gray-200"
                >
                  <div className="space-y-4">
                    {merchant.restrictions.length > 0 && (
                      <div>
                        <h4 className="font-medium text-gray-900 mb-2">Restrictions</h4>
                        <ul className="space-y-1">
                          {merchant.restrictions.map((restriction, index) => (
                            <li key={index} className="flex items-center space-x-2 text-sm text-gray-600">
                              <Ban className="w-3 h-3 text-orange-500" />
                              <span>{restriction}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {merchant.complianceIssues.length > 0 && (
                      <div>
                        <h4 className="font-medium text-gray-900 mb-2">Compliance Issues</h4>
                        <ul className="space-y-1">
                          {merchant.complianceIssues.map((issue, index) => (
                            <li key={index} className="flex items-center space-x-2 text-sm text-red-600">
                              <XCircle className="w-3 h-3" />
                              <span>{issue}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    <div className="text-sm text-gray-500">
                      <p>Last checked: {new Date(merchant.lastChecked).toLocaleString()}</p>
                    </div>
                  </div>
                </motion.div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
