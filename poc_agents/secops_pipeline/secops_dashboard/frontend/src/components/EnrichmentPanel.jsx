import React, { useMemo } from 'react';
import { Doughnut } from 'react-chartjs-2';

const EnrichmentPanel = ({ enrichmentResults }) => {
  // Prepare data for visualization based on enrichment results
  const enrichmentData = useMemo(() => {
    if (!enrichmentResults) return null;
    
    // Extract IOC counts by type and verdict
    const iocTypes = {};
    const verdictCounts = {
      malicious: 0,
      suspicious: 0,
      benign: 0,
      unknown: 0
    };
    
    // Count IOCs by type and verdict
    if (enrichmentResults.iocs) {
      Object.entries(enrichmentResults.iocs).forEach(([ioc, data]) => {
        // Count IOC types
        const type = data.type || 'unknown';
        iocTypes[type] = (iocTypes[type] || 0) + 1;
        
        // Count verdicts
        const verdict = data.verdict?.toLowerCase() || 'unknown';
        if (verdict.includes('malicious')) {
          verdictCounts.malicious += 1;
        } else if (verdict.includes('suspicious')) {
          verdictCounts.suspicious += 1;
        } else if (verdict.includes('benign') || verdict.includes('clean')) {
          verdictCounts.benign += 1;
        } else {
          verdictCounts.unknown += 1;
        }
      });
    }
    
    return {
      iocTypes,
      verdictCounts
    };
  }, [enrichmentResults]);

  // Chart configuration for verdict distribution
  const verdictChartData = useMemo(() => {
    if (!enrichmentData) return null;
    
    return {
      labels: ['Malicious', 'Suspicious', 'Benign', 'Unknown'],
      datasets: [
        {
          data: [
            enrichmentData.verdictCounts.malicious,
            enrichmentData.verdictCounts.suspicious,
            enrichmentData.verdictCounts.benign,
            enrichmentData.verdictCounts.unknown
          ],
          backgroundColor: [
            '#e53e3e', // red for malicious
            '#ed8936', // orange for suspicious
            '#48bb78', // green for benign
            '#718096'  // gray for unknown
          ],
          borderWidth: 1,
        },
      ],
    };
  }, [enrichmentData]);

  const chartOptions = {
    plugins: {
      legend: {
        position: 'right',
        labels: {
          color: '#e2e8f0',
          font: {
            size: 12
          }
        }
      }
    },
    maintainAspectRatio: false
  };

  // Display top IOCs with their verdicts
  const renderIocDetails = () => {
    if (!enrichmentResults?.iocs) return null;
    
    // Get top IOCs to display (prioritize malicious)
    const sortedIocs = Object.entries(enrichmentResults.iocs)
      .sort(([_, dataA], [__, dataB]) => {
        // Sort by verdict severity (malicious > suspicious > unknown > benign)
        const getVerdictScore = (data) => {
          const verdict = data.verdict?.toLowerCase() || '';
          if (verdict.includes('malicious')) return 4;
          if (verdict.includes('suspicious')) return 3;
          if (verdict === 'unknown') return 2;
          return 1; // benign
        };
        
        return getVerdictScore(dataB) - getVerdictScore(dataA);
      })
      .slice(0, 5); // Take top 5
    
    return (
      <div className="mt-4">
        <h3 className="text-md font-medium mb-2">Top IOCs</h3>
        <div className="space-y-2">
          {sortedIocs.map(([ioc, data]) => {
            // Determine verdict styling
            const verdict = data.verdict?.toLowerCase() || 'unknown';
            let verdictColor = 'text-gray-400';
            if (verdict.includes('malicious')) {
              verdictColor = 'text-red-500';
            } else if (verdict.includes('suspicious')) {
              verdictColor = 'text-orange-400';
            } else if (verdict.includes('benign') || verdict.includes('clean')) {
              verdictColor = 'text-green-500';
            }
            
            return (
              <div key={ioc} className="flex justify-between items-center border-b border-gray-700 pb-1">
                <div className="flex items-center">
                  <span className="text-yellow-200 font-medium">{ioc}</span>
                  <span className="ml-2 text-gray-400 text-sm">({data.type || 'unknown'})</span>
                </div>
                <span className={`${verdictColor} font-medium`}>{data.verdict || 'Unknown'}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  if (!enrichmentResults) {
    return (
      <div className="dashboard-card">
        <h2 className="dashboard-card-header">Enrichment</h2>
        <div className="text-gray-400 italic">No enrichment data available</div>
      </div>
    );
  }

  return (
    <div className="dashboard-card">
      <h2 className="dashboard-card-header">Enrichment Results</h2>
      
      <div className="grid grid-cols-2 gap-4">
        {/* Chart View */}
        <div style={{ height: 160 }}>
          {verdictChartData && (
            <Doughnut data={verdictChartData} options={chartOptions} />
          )}
        </div>
        
        {/* IOC Details */}
        <div>{renderIocDetails()}</div>
      </div>
      
      {/* Summary */}
      <div className="mt-4 text-sm">
        <div className="font-medium text-blue-300">Sources:</div>
        <div className="text-gray-400">
          {enrichmentResults.sources?.join(', ') || 'No source information available'}
        </div>
      </div>
    </div>
  );
};

export default EnrichmentPanel;
