import React, { useState, useEffect, useCallback } from 'react';
import ReactFlow, { Background, Controls } from 'reactflow';
import 'reactflow/dist/style.css';
import { Chart, registerables } from 'chart.js';
import { Line, Doughnut, Bar } from 'react-chartjs-2';
import PipelineFlowVisualization from './components/PipelineFlowVisualization';
import AlertDetailsPanel from './components/AlertDetailsPanel';
import EnrichmentPanel from './components/EnrichmentPanel';
import LLMDecisionPanel from './components/LLMDecisionPanel';
import ResponseActionPanel from './components/ResponseActionPanel';
import RecentExecutionsPanel from './components/RecentExecutionsPanel';

// Register Chart.js components
Chart.register(...registerables);

// Backend API URL
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8080';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

function App() {
  const [pipelineState, setPipelineState] = useState({});
  const [events, setEvents] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [activeProjectId, setActiveProjectId] = useState(null);
  const [recentExecutions, setRecentExecutions] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Connect to WebSocket for real-time updates
  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE_URL}/ws`);
    
    ws.onopen = () => {
      console.log('WebSocket connected');
      setWsConnected(true);
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('Received WebSocket data:', data);
        
        // Handle initial data differently
        if (data.type === 'initial_data') {
          setRecentExecutions(data.data.recent_executions || []);
          
          // If we have executions and none selected, select the most recent
          if (data.data.recent_executions?.length > 0 && !activeProjectId) {
            const mostRecent = data.data.recent_executions[0];
            setActiveProjectId(mostRecent.project_id);
            setPipelineState(mostRecent);
          }
          
          setLoading(false);
          return;
        }
        
        // For regular pipeline events
        setEvents(prev => [...prev.slice(-99), data]);
        
        // If this event is for the active project, update state
        if (data.data?.project_id === activeProjectId) {
          setPipelineState(prev => ({
            ...prev,
            ...data.data,
            events: [...(prev.events || []), data]
          }));
        }
        
        // Update recent executions if needed
        if (data.type === 'execution_started' || data.type === 'execution_completed') {
          // Fetch latest executions
          fetchRecentExecutions();
        }
        
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };
    
    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setWsConnected(false);
      // Auto reconnect after 3 seconds
      setTimeout(() => {
        console.log('Attempting to reconnect WebSocket...');
      }, 3000);
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setWsConnected(false);
    };
    
    return () => {
      ws.close();
    };
  }, [activeProjectId]);

  // Fetch recent executions on component mount
  useEffect(() => {
    fetchRecentExecutions();
  }, []);
  
  // When a project is selected, fetch its full state
  useEffect(() => {
    if (activeProjectId) {
      fetchPipelineState(activeProjectId);
    }
  }, [activeProjectId]);
  
  const fetchRecentExecutions = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/recent-executions`);
      const data = await response.json();
      setRecentExecutions(data.executions || []);
      
      // If we don't have an active project and there are executions, select the most recent
      if (!activeProjectId && data.executions?.length > 0) {
        setActiveProjectId(data.executions[0].project_id);
      }
      
      setLoading(false);
    } catch (error) {
      console.error('Error fetching recent executions:', error);
      setLoading(false);
    }
  };
  
  const fetchPipelineState = async (projectId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/pipeline-state/${projectId}`);
      if (response.ok) {
        const data = await response.json();
        setPipelineState(data);
      } else {
        console.error('Failed to fetch pipeline state:', await response.text());
      }
    } catch (error) {
      console.error('Error fetching pipeline state:', error);
    }
  };
  
  const handleProjectSelect = (projectId) => {
    setActiveProjectId(projectId);
  };

  if (loading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-gray-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-4 text-xl text-white">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-4">
      {/* Header */}
      <header className="mb-6 flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">SecOps Pipeline Dashboard</h1>
          <p className="text-gray-400">
            Real-time visibility into security operations pipeline with LLM-enhanced decision making
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <div className={`h-3 w-3 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
          <span className="text-sm text-gray-400">{wsConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </header>
      
      {/* Main Dashboard Grid */}
      <div className="grid grid-cols-12 gap-4">
        {/* Sidebar - Recent Executions */}
        <div className="col-span-3">
          <RecentExecutionsPanel 
            executions={recentExecutions}
            activeProjectId={activeProjectId}
            onSelectProject={handleProjectSelect}
          />
        </div>
        
        {/* Main Content Area */}
        <div className="col-span-9 space-y-4">
          {/* Top Row - Pipeline Flow */}
          <div className="dashboard-card" style={{ height: '240px' }}>
            <h2 className="dashboard-card-header">Pipeline Execution Flow</h2>
            <PipelineFlowVisualization pipelineState={pipelineState} />
          </div>
          
          {/* Middle Row - Alert Details and Enrichment */}
          <div className="grid grid-cols-2 gap-4">
            <AlertDetailsPanel alert={pipelineState.standardized_alert} />
            <EnrichmentPanel enrichmentResults={pipelineState.enrichment_results} />
          </div>
          
          {/* Bottom Row - LLM Decision and Response Action */}
          <div className="grid grid-cols-2 gap-4">
            <LLMDecisionPanel 
              findings={pipelineState.investigation_findings}
              determinedAction={pipelineState.determined_response_action}
              actionParameters={pipelineState.response_action_parameters}
            />
            <ResponseActionPanel 
              responseAction={pipelineState.determined_response_action}
              actionParameters={pipelineState.response_action_parameters}
              actionStatus={pipelineState.response_action_status}
            />
          </div>
        </div>
      </div>
      
      {/* Version Info */}
      <footer className="mt-6 text-center text-gray-500 text-sm">
        <p>SecOps Pipeline v1.0 | Qwen3-8B LLM Integration | AgentVault Framework</p>
      </footer>
    </div>
  );
}

export default App;
