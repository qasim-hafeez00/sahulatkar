"use client"

import React, { useState, useEffect } from "react"
import { motion } from "framer-motion"
import { Play, Pause, Square, RotateCcw, Eye, Code, Globe, Activity, CheckCircle, AlertCircle, Clock, Terminal, Bot, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

interface ExecutionStep {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  duration: number
  details: string
  logs: string[]
}

interface ExecutionTask {
  id: string
  url: string
  product: string
  price: number
  status: 'idle' | 'running' | 'completed' | 'failed'
  startTime: Date | null
  endTime: Date | null
  steps: ExecutionStep[]
  agentId: string
  sessionId: string
}

export function AgenticExecutionEngine() {
  const [tasks, setTasks] = useState<ExecutionTask[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [selectedTask, setSelectedTask] = useState<ExecutionTask | null>(null)
  const [showLogs, setShowLogs] = useState(false)
  const [agentMetrics, setAgentMetrics] = useState({
    totalTasks: 0,
    successRate: 0,
    avgExecutionTime: 0,
    activeAgents: 0
  })

  const createNewTask = (url: string, product: string, price: number) => {
    const newTask: ExecutionTask = {
      id: Math.random().toString(36).substr(2, 9),
      url,
      product,
      price,
      status: 'idle',
      startTime: null,
      endTime: null,
      steps: [
        {
          id: '1',
          name: 'Initialize Playwright Instance',
          status: 'pending',
          duration: 0,
          details: 'Creating isolated browser environment',
          logs: []
        },
        {
          id: '2',
          name: 'Navigate to Product URL',
          status: 'pending',
          duration: 0,
          details: 'Opening product page in browser',
          logs: []
        },
        {
          id: '3',
          name: 'Extract Product Information',
          status: 'pending',
          duration: 0,
          details: 'Using LLM to parse product details',
          logs: []
        },
        {
          id: '4',
          name: 'Add to Cart',
          status: 'pending',
          duration: 0,
          details: 'Simulating user interaction',
          logs: []
        },
        {
          id: '5',
          name: 'Fill Shipping Information',
          status: 'pending',
          duration: 0,
          details: 'Auto-populating delivery details',
          logs: []
        },
        {
          id: '6',
          name: 'Process Payment',
          status: 'pending',
          duration: 0,
          details: 'Executing payment transaction',
          logs: []
        },
        {
          id: '7',
          name: 'Confirm Order',
          status: 'pending',
          duration: 0,
          details: 'Final order confirmation',
          logs: []
        }
      ],
      agentId: `agent-${Math.random().toString(36).substr(2, 6)}`,
      sessionId: `session-${Date.now()}`
    }
    return newTask
  }

  const executeStep = async (task: ExecutionTask, stepIndex: number) => {
    const step = task.steps[stepIndex]
    const stepDuration = 2000 + Math.random() * 3000 // 2-5 seconds per step
    
    // Update step status to running
    setTasks(prev => prev.map(t => {
      if (t.id === task.id) {
        const updatedSteps = [...t.steps]
        updatedSteps[stepIndex] = {
          ...updatedSteps[stepIndex],
          status: 'running',
          logs: [`[${new Date().toISOString()}] Starting: ${step.name}`]
        }
        return { ...t, steps: updatedSteps }
      }
      return t
    }))

    // Simulate step execution with logs
    const logs = generateStepLogs(step.name)
    for (let i = 0; i < logs.length; i++) {
      await new Promise(resolve => setTimeout(resolve, stepDuration / logs.length))
      
      setTasks(prev => prev.map(t => {
        if (t.id === task.id) {
          const updatedSteps = [...t.steps]
          updatedSteps[stepIndex] = {
            ...updatedSteps[stepIndex],
            logs: [...updatedSteps[stepIndex].logs, logs[i]]
          }
          return { ...t, steps: updatedSteps }
        }
        return t
      }))
    }

    // Complete the step
    const stepSuccess = Math.random() > 0.05 // 95% success rate
    setTasks(prev => prev.map(t => {
      if (t.id === task.id) {
        const updatedSteps = [...t.steps]
        updatedSteps[stepIndex] = {
          ...updatedSteps[stepIndex],
          status: stepSuccess ? 'completed' : 'failed',
          duration: stepDuration,
          logs: [...updatedSteps[stepIndex].logs, 
            `[${new Date().toISOString()}] ${stepSuccess ? 'SUCCESS' : 'FAILED'}: ${step.name}`
          ]
        }
        return { ...t, steps: updatedSteps }
      }
      return t
    }))

    return stepSuccess
  }

  const generateStepLogs = (stepName: string): string[] => {
    const logTemplates = {
      'Initialize Playwright Instance': [
        'Creating isolated browser container',
        'Configuring user agent rotation',
        'Setting up proxy network',
        'Initializing browser context'
      ],
      'Navigate to Product URL': [
        'Opening browser tab',
        'Navigating to product URL',
        'Waiting for page load',
        'Checking page responsiveness'
      ],
      'Extract Product Information': [
        'Scanning DOM for product elements',
        'Running LLM inference on page content',
        'Extracting product metadata',
        'Validating product information'
      ],
      'Add to Cart': [
        'Locating add to cart button',
        'Simulating mouse movement',
        'Calculating optimal click trajectory',
        'Executing click action'
      ],
      'Fill Shipping Information': [
        'Detecting form fields',
        'Populating shipping details',
        'Validating form inputs',
        'Submitting shipping form'
      ],
      'Process Payment': [
        'Selecting payment method',
        'Entering payment details',
        'Validating payment information',
        'Authorizing transaction'
      ],
      'Confirm Order': [
        'Reviewing order summary',
        'Confirming purchase',
        'Generating order confirmation',
        'Recording transaction details'
      ]
    }
    
    return logTemplates[stepName as keyof typeof logTemplates] || ['Processing step...']
  }

  const runExecution = async (task: ExecutionTask) => {
    setIsRunning(true)
    
    // Start task
    setTasks(prev => prev.map(t => {
      if (t.id === task.id) {
        return { 
          ...t, 
          status: 'running', 
          startTime: new Date() 
        }
      }
      return t
    }))

    // Execute all steps
    for (let i = 0; i < task.steps.length; i++) {
      const success = await executeStep(task, i)
      if (!success) {
        // Stop execution if step fails
        setTasks(prev => prev.map(t => {
          if (t.id === task.id) {
            return { 
              ...t, 
              status: 'failed', 
              endTime: new Date() 
            }
          }
          return t
        }))
        setIsRunning(false)
        return
      }
    }

    // Complete task
    setTasks(prev => prev.map(t => {
      if (t.id === task.id) {
        return { 
          ...t, 
          status: 'completed', 
          endTime: new Date() 
        }
      }
      return t
    }))

    setIsRunning(false)
    updateMetrics()
  }

  const updateMetrics = () => {
    setTasks(prev => {
      const completedTasks = prev.filter(t => t.status === 'completed')
      const totalTasks = prev.filter(t => t.status !== 'idle')
      const successRate = totalTasks.length > 0 ? (completedTasks.length / totalTasks.length) * 100 : 0
      const avgTime = completedTasks.length > 0 
        ? completedTasks.reduce((sum, task) => {
            const duration = task.endTime && task.startTime 
              ? (task.endTime.getTime() - task.startTime.getTime()) / 1000 
              : 0
            return sum + duration
          }, 0) / completedTasks.length 
        : 0

      setAgentMetrics({
        totalTasks: totalTasks.length,
        successRate: Math.round(successRate),
        avgExecutionTime: Math.round(avgTime),
        activeAgents: prev.filter(t => t.status === 'running').length
      })

      return prev
    })
  }

  const addSampleTask = () => {
    const sampleUrls = [
      { url: 'https://www.daraz.pk/iphone-15-pro', product: 'iPhone 15 Pro 256GB', price: 299999 },
      { url: 'https://www.amazon.com/macbook-air-m2', product: 'MacBook Air M2 512GB', price: 249999 },
      { url: 'https://www.naheed.lk/samsung-tv-55', product: 'Samsung 55" QLED TV', price: 149999 }
    ]
    
    const randomSample = sampleUrls[Math.floor(Math.random() * sampleUrls.length)]
    const newTask = createNewTask(randomSample.url, randomSample.product, randomSample.price)
    setTasks(prev => [...prev, newTask])
  }

  const resetTask = (taskId: string) => {
    setTasks(prev => prev.map(t => {
      if (t.id === taskId) {
        return {
          ...t,
          status: 'idle',
          startTime: null,
          endTime: null,
          steps: t.steps.map(step => ({
            ...step,
            status: 'pending',
            duration: 0,
            logs: []
          }))
        }
      }
      return t
    }))
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-600 bg-green-100'
      case 'running': return 'text-blue-600 bg-blue-100'
      case 'failed': return 'text-red-600 bg-red-100'
      default: return 'text-gray-600 bg-gray-100'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-4 h-4" />
      case 'running': return <Activity className="w-4 h-4 animate-pulse" />
      case 'failed': return <AlertCircle className="w-4 h-4" />
      default: return <Clock className="w-4 h-4" />
    }
  }

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Button onClick={addSampleTask} disabled={isRunning}>
            <Bot className="w-4 h-4 mr-2" />
            Add Task
          </Button>
          <Button variant="outline" onClick={updateMetrics}>
            <Activity className="w-4 h-4 mr-2" />
            Refresh Metrics
          </Button>
        </div>
        
        <div className="flex items-center space-x-6 text-sm">
          <div className="flex items-center space-x-2">
            <Terminal className="w-4 h-4 text-gray-500" />
            <span className="text-gray-600">Active Agents: {agentMetrics.activeAgents}</span>
          </div>
          <div className="flex items-center space-x-2">
            <Zap className="w-4 h-4 text-green-500" />
            <span className="text-gray-600">Success Rate: {agentMetrics.successRate}%</span>
          </div>
        </div>
      </div>

      {/* Tasks Grid */}
      <div className="grid gap-4">
        {tasks.map((task) => (
          <Card key={task.id} className="border-0 shadow-medium">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-4">
                  <div className={`w-3 h-3 rounded-full ${
                    task.status === 'running' ? 'bg-blue-500 animate-pulse' :
                    task.status === 'completed' ? 'bg-green-500' :
                    task.status === 'failed' ? 'bg-red-500' : 'bg-gray-300'
                  }`} />
                  <div>
                    <h3 className="font-semibold text-gray-900">{task.product}</h3>
                    <p className="text-sm text-gray-600">{task.url}</p>
                    <p className="text-sm font-medium text-orange-600">PKR {task.price.toLocaleString()}</p>
                  </div>
                </div>
                
                <div className="flex items-center space-x-2">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium flex items-center space-x-1 ${getStatusColor(task.status)}`}>
                    {getStatusIcon(task.status)}
                    <span>{task.status.toUpperCase()}</span>
                  </span>
                  
                  <div className="flex items-center space-x-1">
                    {task.status === 'idle' && (
                      <Button 
                        size="sm" 
                        onClick={() => runExecution(task)}
                        disabled={isRunning}
                      >
                        <Play className="w-3 h-3" />
                      </Button>
                    )}
                    {task.status === 'running' && (
                      <Button size="sm" variant="outline">
                        <Pause className="w-3 h-3" />
                      </Button>
                    )}
                    <Button 
                      size="sm" 
                      variant="outline"
                      onClick={() => resetTask(task.id)}
                    >
                      <RotateCcw className="w-3 h-3" />
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline"
                      onClick={() => setSelectedTask(task)}
                    >
                      <Eye className="w-3 h-3" />
                    </Button>
                  </div>
                </div>
              </div>

              {/* Progress Steps */}
              <div className="space-y-2">
                {task.steps.map((step, index) => (
                  <div key={step.id} className="flex items-center space-x-3">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                      step.status === 'completed' ? 'bg-green-100 text-green-600' :
                      step.status === 'running' ? 'bg-blue-100 text-blue-600' :
                      step.status === 'failed' ? 'bg-red-100 text-red-600' : 'bg-gray-100 text-gray-400'
                    }`}>
                      {step.status === 'completed' ? <CheckCircle className="w-4 h-4" /> :
                       step.status === 'running' ? <Activity className="w-4 h-4 animate-pulse" /> :
                       step.status === 'failed' ? <AlertCircle className="w-4 h-4" /> :
                       <Clock className="w-4 h-4" />}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-gray-900">{step.name}</span>
                        {step.duration > 0 && (
                          <span className="text-xs text-gray-500">{(step.duration / 1000).toFixed(1)}s</span>
                        )}
                      </div>
                      <p className="text-xs text-gray-600">{step.details}</p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Task Details */}
              {selectedTask?.id === task.id && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="mt-4 pt-4 border-t border-gray-200"
                >
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium text-gray-900">Execution Details</h4>
                    <Button 
                      size="sm" 
                      variant="outline"
                      onClick={() => setShowLogs(!showLogs)}
                    >
                      <Code className="w-3 h-3 mr-1" />
                      {showLogs ? 'Hide' : 'Show'} Logs
                    </Button>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-600">Agent ID:</span>
                      <span className="ml-2 font-mono text-gray-900">{task.agentId}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">Session ID:</span>
                      <span className="ml-2 font-mono text-gray-900">{task.sessionId}</span>
                    </div>
                    {task.startTime && (
                      <div>
                        <span className="text-gray-600">Started:</span>
                        <span className="ml-2 text-gray-900">{task.startTime.toLocaleTimeString()}</span>
                      </div>
                    )}
                    {task.endTime && (
                      <div>
                        <span className="text-gray-600">Completed:</span>
                        <span className="ml-2 text-gray-900">{task.endTime.toLocaleTimeString()}</span>
                      </div>
                    )}
                  </div>

                  {showLogs && (
                    <div className="mt-4">
                      <h5 className="font-medium text-gray-900 mb-2">Execution Logs</h5>
                      <div className="bg-gray-900 text-green-400 p-3 rounded-lg font-mono text-xs max-h-40 overflow-y-auto">
                        {task.steps.flatMap(step => step.logs).map((log, index) => (
                          <div key={index}>{log}</div>
                        ))}
                      </div>
                    </div>
                  )}
                </motion.div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {tasks.length === 0 && (
        <Card className="border-0 shadow-medium">
          <CardContent className="p-12 text-center">
            <Bot className="w-16 h-16 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-gray-900 mb-2">No Active Tasks</h3>
            <p className="text-gray-600 mb-4">Add a task to start the agentic execution engine</p>
            <Button onClick={addSampleTask}>
              <Bot className="w-4 h-4 mr-2" />
              Add Sample Task
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
