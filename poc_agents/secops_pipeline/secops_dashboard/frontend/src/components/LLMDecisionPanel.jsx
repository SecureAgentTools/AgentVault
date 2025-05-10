import React, { useMemo } from 'react';
import { Bar } from 'react-chartjs-2';

const LLMDecisionPanel = ({ findings, determinedAction, actionParameters }) => {
  // Extract confidence scores and other metrics from findings
  const decisionData = useMemo(() => {
    if (!findings) return null;
    
    // Extract key metrics
    const confidence = findings.confidence || 0;
    const severity = findings.severity || 'unknown';
    
    // Format severity for display
    let severityFormatted = 'Unknown';
    let severityColor = 'text-gray-400';
    
    if (typeof severity === 'string') {
      // Format the severity string
      severityFormatted = severity.charAt(0).toUpperCase() + severity.slice(1).toLowerCase();
      
      // Set color based on severity
      if (severityFormatted.toLowerCase() === 'critical' || severityFormatted.toLowerCase() === 'high') {
        severityColor = 'text-red-500';
      } else if (severityFormatted.toLowerCase() === 'medium') {
        severityColor = 'text-yellow-500';
      } else if (severityFormatted.toLowerCase() === 'low') {
        severityColor = 'text-green-500';
      }
    }
    
    return {
      confidence,
      severity: severityFormatted,
      severityColor,
      summary: findings.summary || 'No summary provided',
      llmResponses: findings.llm_responses || findings.analysis || findings.details || null,
    };
  }, [findings]);

  // Prepare confidence chart data
  const confidenceChartData = useMemo(() => {
    if (!decisionData) return null;
    
    return {
      labels: ['Confidence'],
      datasets: [
        {
          label: 'Confidence Score',
          data: [decisionData.confidence * 100], // Convert to percentage
          backgroundColor: [
            decisionData.confidence >= 0.75 ? '#48bb78' : 
            decisionData.confidence >= 0.5 ? '#ed8936' : '#e53e3e'
          ],
          borderWidth: 1,
        },
      ],
    };
  }, [decisionData]);

  const chartOptions = {
    scales: {
      y: {
        beginAtZero: true,
        max: 100,
        ticks: {
          color: '#e2e8f0'
        },
        grid: {
          color: '#2d3748'
        }
      },
      x: {
        ticks: {
          color: '#e2e8f0'
        },
        grid: {
          color: '#2d3748'
        }
      }
    },
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        callbacks: {
          label: function(context) {
            return `Confidence: ${context.raw}%`;
          }
        }
      }
    },
    maintainAspectRatio: false
  };

  // Format the determined action for display
  const formatAction = (action) => {
    if (!action) return 'None';
    
    return action
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  };

  if (!findings) {
    return (
      <div className="dashboard-card">
        <h2 className="dashboard-card-header">LLM Decision</h2>
        <div className="text-gray-400 italic">No investigation findings available</div>
      </div>
    );
  }

  return (
    <div className="dashboard-card">
      <h2 className="dashboard-card-header">LLM-Enhanced Decision</h2>
      
      <div className="grid grid-cols-2 gap-4">
        {/* Left Column: Metrics and Decision */}
        <div className="space-y-4">
          {/* Key Metrics */}
          <div>
            <div className="mb-2">
              <span className="text-gray-400">Severity: </span>
              <span className={`font-medium ${decisionData.severityColor}`}>
                {decisionData.severity}
              </span>
            </div>
            
            <div className="mb-2">
              <span className="text-gray-400">Confidence: </span>
              <span className="font-medium">
                {Math.round(decisionData.confidence * 100)}%
              </span>
            </div>
            
            <div className="mb-2">
              <span className="text-gray-400">Determined Action: </span>
              <span className="font-medium text-blue-300">
                {formatAction(determinedAction)}
              </span>
            </div>
          </div>
          
          {/* LLM Reasoning */}
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-1">LLM Reasoning:</h3>
            <div className="text-gray-400 text-sm max-h-24 overflow-y-auto">
              {decisionData.llmResponses ? (
                typeof decisionData.llmResponses === 'string' ? 
                  decisionData.llmResponses :
                  JSON.stringify(decisionData.llmResponses, null, 2)
              ) : (
                <span className="italic">No detailed reasoning available</span>
              )}
            </div>
          </div>
        </div>
        
        {/* Right Column: Confidence Visualization */}
        <div>
          <div style={{ height: 150 }}>
            {confidenceChartData && (
              <Bar data={confidenceChartData} options={chartOptions} />
            )}
          </div>
          
          {/* Summary */}
          <div className="mt-4">
            <h3 className="text-sm font-medium text-gray-300 mb-1">Summary:</h3>
            <div className="text-sm text-white">
              {decisionData.summary}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LLMDecisionPanel;
