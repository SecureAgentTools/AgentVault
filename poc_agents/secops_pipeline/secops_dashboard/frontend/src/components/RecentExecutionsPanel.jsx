import React from 'react';

const RecentExecutionsPanel = ({ executions, activeProjectId, onSelectProject }) => {
  // Format date string for display
  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown';
    
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch (e) {
      return dateStr;
    }
  };
  
  // Get status color based on execution status
  const getStatusColor = (status) => {
    if (!status) return 'bg-gray-500';
    
    if (status === 'COMPLETED') {
      return 'bg-green-500';
    } else if (status === 'FAILED') {
      return 'bg-red-500';
    } else if (status === 'WORKING') {
      return 'bg-blue-500';
    } else {
      return 'bg-yellow-500';
    }
  };
  
  // Get formatted alert name for display
  const getAlertName = (execution) => {
    if (!execution) return 'Unknown Alert';
    
    // Try to extract alert name from standardized_alert
    if (execution.standardized_alert?.name) {
      return execution.standardized_alert.name;
    }
    
    // Try to extract from original alert
    if (execution.initial_alert_data?.name) {
      return execution.initial_alert_data.name;
    }
    
    // Fall back to project ID
    return `Alert ${execution.project_id?.substring(0, 8) || 'Unknown'}`;
  };

  if (!executions || executions.length === 0) {
    return (
      <div className="dashboard-card h-full">
        <h2 className="dashboard-card-header">Recent Executions</h2>
        <div className="text-gray-400 italic">No pipeline executions found</div>
      </div>
    );
  }

  return (
    <div className="dashboard-card h-full">
      <h2 className="dashboard-card-header">Recent Executions</h2>
      
      <div className="space-y-1">
        {executions.map((execution) => (
          <div 
            key={execution.project_id} 
            className={`p-2 rounded cursor-pointer transition-colors duration-150 
              ${execution.project_id === activeProjectId 
                ? 'bg-blue-900 border-l-4 border-blue-500' 
                : 'hover:bg-gray-700'}`}
            onClick={() => onSelectProject(execution.project_id)}
          >
            <div className="font-medium mb-1 truncate">
              {getAlertName(execution)}
            </div>
            
            <div className="flex justify-between items-center text-xs">
              <div className="text-gray-400">
                {formatDate(execution.last_updated)}
              </div>
              
              <div className="flex items-center">
                <div className={`h-2 w-2 rounded-full ${getStatusColor(execution.status)} mr-1`}></div>
                <span className="text-gray-300">{execution.status || 'Unknown'}</span>
              </div>
            </div>
            
            {/* Alert Source/Type if available */}
            {(execution.standardized_alert?.source || execution.standardized_alert?.type) && (
              <div className="text-xs text-gray-500 mt-1">
                {execution.standardized_alert?.source || execution.standardized_alert?.type}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default RecentExecutionsPanel;
