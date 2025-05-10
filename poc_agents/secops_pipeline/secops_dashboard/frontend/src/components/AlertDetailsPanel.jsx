import React from 'react';

const AlertDetailsPanel = ({ alert }) => {
  if (!alert) {
    return (
      <div className="dashboard-card">
        <h2 className="dashboard-card-header">Alert Details</h2>
        <div className="text-gray-400 italic">No alert data available</div>
      </div>
    );
  }

  // Function to determine if a field might contain an IOC
  const isIocField = (key, value) => {
    const iocKeys = [
      'ip', 'address', 'domain', 'url', 'hash', 'md5', 'sha256', 'sha1', 
      'hostname', 'host', 'email', 'source', 'destination', 'src', 'dst'
    ];
    
    // Check if the key contains any IOC-related strings
    const keyContainsIocTerm = iocKeys.some(iocKey => 
      key.toLowerCase().includes(iocKey.toLowerCase())
    );
    
    // Check if the value looks like an IP address
    const isIpAddress = typeof value === 'string' && 
      /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/.test(value);
    
    // Check if the value looks like a domain or URL
    const isDomainOrUrl = typeof value === 'string' &&
      (value.includes('.com') || value.includes('.net') || value.includes('.org') || 
       value.includes('http') || value.startsWith('www.'));
    
    // Check if the value looks like a hash
    const isHash = typeof value === 'string' && 
      /^[a-fA-F0-9]{32,64}$/.test(value);
    
    return keyContainsIocTerm || isIpAddress || isDomainOrUrl || isHash;
  };

  // Extract and display key alert information
  const renderAlertData = () => {
    // First display important summary fields
    const importantFields = ['name', 'type', 'severity', 'time', 'date', 'description', 'summary'];
    const importantData = {};
    const iocData = {};
    const otherData = {};
    
    // Categorize fields
    Object.entries(alert).forEach(([key, value]) => {
      if (importantFields.includes(key.toLowerCase())) {
        importantData[key] = value;
      } else if (isIocField(key, value)) {
        iocData[key] = value;
      } else if (typeof value !== 'object') {
        otherData[key] = value;
      }
    });
    
    return (
      <div className="space-y-4">
        {/* Basic information */}
        <div>
          {Object.entries(importantData).map(([key, value]) => (
            <div key={key} className="grid grid-cols-3 mb-1">
              <div className="text-gray-400 capitalize">{key.replace(/_/g, ' ')}:</div>
              <div className="col-span-2">{String(value)}</div>
            </div>
          ))}
        </div>
        
        {/* IOC information */}
        {Object.keys(iocData).length > 0 && (
          <div>
            <h3 className="text-md font-medium text-blue-300 mb-2">Indicators of Compromise</h3>
            {Object.entries(iocData).map(([key, value]) => (
              <div key={key} className="grid grid-cols-3 mb-1">
                <div className="text-gray-400 capitalize">{key.replace(/_/g, ' ')}:</div>
                <div className="col-span-2 text-yellow-200 font-medium">{String(value)}</div>
              </div>
            ))}
          </div>
        )}
        
        {/* Other relevant information */}
        {Object.keys(otherData).length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-gray-400 mb-2">Additional Information</h3>
            {Object.entries(otherData).map(([key, value]) => (
              <div key={key} className="grid grid-cols-3 mb-1">
                <div className="text-gray-500 capitalize text-sm">{key.replace(/_/g, ' ')}:</div>
                <div className="col-span-2 text-sm">{String(value)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="dashboard-card">
      <h2 className="dashboard-card-header">Alert Details</h2>
      {renderAlertData()}
    </div>
  );
};

export default AlertDetailsPanel;
