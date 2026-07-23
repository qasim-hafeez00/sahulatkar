"use client"

import React, { motion, AnimatePresence } from "framer-motion"
import { useState, useRef, useEffect } from "react"
import { MessageCircle, X, Send, Bot, User, Clock, CheckCircle, Brain, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

interface Message {
  id: string
  text: string
  sender: 'user' | 'bot'
  timestamp: Date
  typing?: boolean
  intent?: string
  entities?: string[]
  confidence?: number
  suggestedActions?: string[]
}

interface NLPResponse {
  text: string
  intent: string
  entities: string[]
  confidence: number
  suggestedActions: string[]
  context: string
}

const quickActions = [
  "Check my order status",
  "What are my repayment options?",
  "How does financing work?",
  "Contact support agent"
]

const botResponses = {
  "order status": "I can help you check your order status. Please provide your order number, or I can look up your recent orders.",
  "repayment": "You have several repayment options available: 1) Auto-debit via Raast, 2) Manual bank transfer, 3) EasyPaisa/JazzCash. Your next payment is due in 3 days for PKR 25,000.",
  "financing": "Our Shariah-compliant financing works through the Agency Murabaha model. We purchase the product on your behalf and sell it to you at a cost-plus-profit price with transparent terms.",
  "support": "I'm connecting you with a human support agent. The wait time is approximately 2 minutes."
}

const processNLP = async (text: string, currentContext: string[]): Promise<NLPResponse> => {
  // Simulate NLP processing
  await new Promise(resolve => setTimeout(resolve, 1500))
  
  const lowerText = text.toLowerCase()
  let intent = 'general'
  let entities: string[] = []
  let confidence = 0.85
  let suggestedActions: string[] = []
  let responseText = "I understand you're asking about this. Let me help you with that."
  
  // Intent detection
  if (lowerText.includes('order') || lowerText.includes('status') || lowerText.includes('delivery')) {
    intent = 'order_status'
    confidence = 0.92
    responseText = "I can help you check your order status. Please provide your order number, or I can look up your recent orders."
    suggestedActions = ["View recent orders", "Track by order number", "Contact support"]
    
    // Entity extraction
    if (lowerText.match(/ord-\d+/)) {
      entities.push('order_number')
    }
  } else if (lowerText.includes('repayment') || lowerText.includes('pay') || lowerText.includes('installment')) {
    intent = 'repayment'
    confidence = 0.89
    responseText = "You have several repayment options available: 1) Auto-debit via Raast, 2) Manual bank transfer, 3) EasyPaisa/JazzCash. Your next payment is due in 3 days for PKR 25,000."
    suggestedActions = ["Make payment now", "View payment history", "Set up auto-debit"]
    
    if (lowerText.includes('raast')) entities.push('payment_method')
    if (lowerText.match(/\d+/)) entities.push('amount')
  } else if (lowerText.includes('financing') || lowerText.includes('loan') || lowerText.includes('murabaha')) {
    intent = 'financing'
    confidence = 0.94
    responseText = "Our Shariah-compliant financing works through the Agency Murabaha model. We purchase the product on your behalf and sell it to you at a cost-plus-profit price with transparent terms."
    suggestedActions = ["Apply for financing", "Calculate payments", "View terms"]
  } else if (lowerText.includes('support') || lowerText.includes('help') || lowerText.includes('agent')) {
    intent = 'support'
    confidence = 0.88
    responseText = "I'm connecting you with a human support agent. The wait time is approximately 2 minutes."
    suggestedActions = ["Start live chat", "Schedule callback", "Email support"]
  } else if (lowerText.includes('hello') || lowerText.includes('hi') || lowerText.includes('hey')) {
    intent = 'greeting'
    confidence = 0.96
    responseText = "Hello! I'm here to help. What can I assist you with today?"
    suggestedActions = ["Check order status", "View financing options", "Make a payment"]
  } else if (lowerText.includes('thank') || lowerText.includes('thanks')) {
    intent = 'gratitude'
    confidence = 0.93
    responseText = "You're welcome! Is there anything else I can help you with?"
    suggestedActions = ["Yes, I need more help", "No, that's all for now"]
  } else {
    // Fallback response with contextual understanding
    if (currentContext.length > 0 && currentContext[currentContext.length - 1] === 'order_status') {
      responseText = "Regarding your order, I can help you track it. What specific information do you need?"
      suggestedActions = ["Track order", "Modify order", "Cancel order"]
    } else {
      responseText = "I'm here to help with orders, payments, financing, and general support. Could you please be more specific about what you need?"
      suggestedActions = ["Order status", "Payment options", "Financing information", "Contact support"]
    }
    confidence = 0.65
  }
  
  return {
    text: responseText,
    intent,
    entities,
    confidence,
    suggestedActions,
    context: intent
  }
}

export function ChatbotWidget() {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      text: "Hello! I'm your AI assistant powered by advanced NLP. How can I help you today?",
      sender: 'bot',
      timestamp: new Date()
    }
  ])
  const [inputText, setInputText] = useState("")
  const [isTyping, setIsTyping] = useState(false)
  const [isProcessingNLP, setIsProcessingNLP] = useState(false)
  const [context, setContext] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const generateBotResponse = (userInput: string): string => {
    const input = userInput.toLowerCase()
    
    for (const [key, response] of Object.entries(botResponses)) {
      if (input.includes(key)) {
        return response
      }
    }
    
    return "I understand you're asking about: " + userInput + ". Let me help you with that. Could you provide more details so I can assist you better?"
  }

  const sendMessage = async () => {
    if (!inputText.trim()) return

    const userMessage: Message = {
      id: Date.now().toString(),
      text: inputText,
      sender: 'user',
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setInputText("")
    setIsTyping(true)
    setIsProcessingNLP(true)

    // Process with NLP
    try {
      const nlpResponse = await processNLP(inputText, context)
      
      // Update context
      setContext(prev => [...prev, nlpResponse.context])
      
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: nlpResponse.text,
        sender: 'bot',
        timestamp: new Date(),
        intent: nlpResponse.intent,
        entities: nlpResponse.entities,
        confidence: nlpResponse.confidence,
        suggestedActions: nlpResponse.suggestedActions
      }
      
      setMessages(prev => [...prev, botMessage])
    } catch (error) {
      // Fallback response
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: "I'm having trouble processing that. Could you please rephrase your question?",
        sender: 'bot',
        timestamp: new Date()
      }
      setMessages(prev => [...prev, botMessage])
    } finally {
      setIsTyping(false)
      setIsProcessingNLP(false)
    }
  }

  const handleQuickAction = (action: string) => {
    setInputText(action)
    setTimeout(() => sendMessage(), 100)
  }

  return (
    <>
      {/* Chat Button */}
      <motion.div
        className="fixed z-[9999]"
        style={{
          right: "24px",
          bottom: "calc(24px + env(safe-area-inset-bottom))",
        }}
        initial={{ y: 20, opacity: 0, scale: 0.9 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 25, delay: 0.1 }}
      >
        <Button
          onClick={() => setIsOpen(!isOpen)}
          size="lg"
          className="w-14 h-14 rounded-full bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 shadow-lg hover:shadow-xl transition-all duration-300"
        >
          <AnimatePresence mode="wait">
            {isOpen ? (
              <motion.div
                key="close"
                initial={{ rotate: 0, opacity: 0 }}
                animate={{ rotate: 180, opacity: 1 }}
                exit={{ rotate: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <X className="w-6 h-6" />
              </motion.div>
            ) : (
              <motion.div
                key="open"
                initial={{ rotate: -180, opacity: 0 }}
                animate={{ rotate: 0, opacity: 1 }}
                exit={{ rotate: -180, opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <MessageCircle className="w-6 h-6" />
              </motion.div>
            )}
          </AnimatePresence>
        </Button>
      </motion.div>

      {/* Chat Window */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.9 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="fixed w-80 sm:w-96 h-[600px] theme-panel rounded-2xl shadow-2xl z-[9999] flex flex-col"
            style={{ right: '24px', bottom: 'calc(96px + env(safe-area-inset-bottom))' }}
          >
            {/* Header */}
            <div className="bg-gradient-to-r from-orange-500 to-orange-600 text-white p-4 rounded-t-2xl">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center">
                    <Bot className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="font-semibold">AI Assistant</h3>
                    <div className="flex items-center space-x-1">
                      <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                      <span className="text-xs opacity-90">Online</span>
                    </div>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsOpen(false)}
                  className="text-white hover:bg-white/20"
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.map((message) => (
                <motion.div
                  key={message.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`max-w-[80%] ${message.sender === 'user' ? 'order-2' : 'order-1'}`}>
                    <div className={`flex items-end space-x-2 ${message.sender === 'user' ? 'flex-row-reverse space-x-reverse' : ''}`}>
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                        message.sender === 'user' 
                          ? 'bg-orange-500 text-white' 
                          : 'bg-gray-200 text-gray-600'
                      }`}>
                        {message.sender === 'user' ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                      </div>
                      <div className={`rounded-2xl px-4 py-2 ${
                        message.sender === 'user'
                          ? 'bg-orange-500 text-white'
                          : 'bg-gray-100 text-gray-900'
                      }`}>
                        <p className="text-sm">{message.text}</p>
                        <div className={`flex items-center space-x-1 mt-1 text-xs ${
                          message.sender === 'user' ? 'text-orange-200' : 'text-gray-500'
                        }`}>
                          <Clock className="w-3 h-3" />
                          <span>{message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              ))}

              {isTyping && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex justify-start"
                >
                  <div className="flex items-end space-x-2">
                    <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center">
                      <Bot className="w-4 h-4 text-gray-600" />
                    </div>
                    <div className="bg-gray-100 rounded-2xl px-4 py-3">
                      <div className="flex space-x-1">
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Quick Actions */}
            <div className="px-4 py-2 border-t border-gray-200">
              <div className="flex flex-wrap gap-2">
                {quickActions.map((action) => (
                  <Button
                    key={action}
                    variant="outline"
                    size="sm"
                    onClick={() => handleQuickAction(action)}
                    className="text-xs bg-gray-50 hover:bg-gray-100 border-gray-200"
                  >
                    {action}
                  </Button>
                ))}
              </div>
            </div>

            {/* Input */}
            <div className="p-4 border-t border-gray-200">
              <div className="flex space-x-2">
                <Input
                  placeholder="Type your message..."
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                  className="flex-1"
                />
                <Button
                  onClick={sendMessage}
                  disabled={!inputText.trim()}
                  className="bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700"
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
