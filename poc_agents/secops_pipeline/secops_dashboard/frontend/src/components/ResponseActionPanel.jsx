import React from 'react';

const ResponseActionPanel = ({ responseAction, actionParameters, actionStatus }) => {
  // Format the response action for display
  const formatAction = (action) => {
    if (!action) return 'None';
    
    return action
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  };
  
  // Get status color based on action status
  const getStatusColor = (status) => {
    if (!status) return 'bg-gray-500';
    
    const statusStr = typeof status === 'string' ? status : status.status;
    
    if (!statusStr) return 'bg-gray-500';
    
    if (statusStr.toLowerCase().includes('success')) {
      return 'bg-green-500';
    } else if (statusStr.toLowerCase().includes('error') || statusStr.toLowerCase().includes('failed')) {
      return 'bg-red-500';
    } else if (statusStr.toLowerCase().includes('progress') || statusStr.toLowerCase().includes('working')) {
      return 'bg-blue-500';
    } else if (statusStr.toLowerCase().includes('pending')) {
      return 'bg-yellow-500';
    }
    
    return 'bg-gray-500';
  };
  
  // Render actionable parameters in a readable format
  const renderParameters = () => {
    if (!actionParameters) return <div className="text-gray-400 italic">No parameters available</div>;
    
    return (
      <div className="space-y-2 max-h-40 overflow-y-auto">
        {Object.entries(actionParameters).map(([key, value]) => (
          <div key={key} className="grid grid-cols-3 gap-2">
            <div className="text-gray-400 capitalize">{key.replace(/_/g, ' ')}:</div>
            <div className="col-span-2 text-sm">
              {typeof value === 'object' 
                ? JSON.stringify(value)
                : String(value)}
            </div>
          </div>
        ))}
      </div>
    );
  };
  
  // Render response execution status and details
  const renderExecutionStatus = () => {
    if (!actionStatus) {
      return (
        <div className="flex items-center">
          <div className="h-3 w-3 rounded-full bg-gray-500 mr-2"></div>
          <span className="text-gray-400">Not executed yet</span>
        </div>
      );
    }
    
    const status = typeof actionStatus === 'string' ? actionStatus : actionStatus.status;
    const details = typeof actionStatus === 'object' ? actionStatus.details : null;
    
    return (
      <div>
        <div className="flex items-center mb-2">
          <div className={`h-3 w-3 rounded-full ${getStatusColor(status)} mr-2`}></div>
          <span className="font-medium">
            {typeof status === 'string' ? status : 'Unknown'}
          </span>
        </div>
        
        {details && (
          <div className="text-sm text-gray-300 mt-2">
            <div className="font-medium mb-1">Execution Details:</div>
            {typeof details === 'object' ? (
              <div className="bg-gray-700 p-2 rounded text-xs overflow-x-auto">
                <pre>{JSON.stringify(details, null, 2)}</pre>
              </div>
            ) : (
              <div>{String(details)}</div>
            )}
          </div>
        )}
      </div>
    );
  };

  if (!responseAction) {
    return (
      <div className="dashboard-card">
        <h2 className="dashboard-card-header">Response Action</h2>
        <div className="text-gray-400 italic">No response action determined yet</div>
      </div>
    );
  }

  return (
    <div className="dashboard-card">
      <h2 className="dashboard-card-header">Response Action Execution</h2>
      
      <div className="space-y-4">
        {/* Action Type */}
        <div>
          <div className="text-gray-400 mb-1">Action Type:</div>
          <div className="text-lg font-medium text-blue-300">
            {formatAction(responseAction)}
          </div>
        </div>
        
        {/* Execution Status */}
        <div>
          <div className="text-gray-400 mb-1">Execution Status:</div>
          {renderExecutionStatus()}
        </div>
        
        {/* Parameters */}
        <div>
          <div className="text-gray-400 mb-1">Action Parameters:</div>
          {renderParameters()}
        </div>
      </div>
    </div>
  );
};

export default ResponseActionPanel;
