import React, { useMemo } from 'react';
import ReactFlow, { 
  Background, 
  Controls, 
  Handle, 
  Position,
  MarkerType
} from 'reactflow';
import 'reactflow/dist/style.css';

// Custom node component
function PipelineStepNode({ data }) {
  return (
    <div className={`pipeline-node node-${data.status}`}>
      <Handle type="target" position={Position.Left} />
      <div className="font-semibold">{data.label}</div>
      {data.status === 'active' && (
        <div className="text-xs mt-1">Processing...</div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

// Node types for customizing appearance
const nodeTypes = {
  pipelineStep: PipelineStepNode,
};

// Pipeline step node IDs in order
const PIPELINE_STEPS = [
  'start_pipeline',
  'ingest_alert',
  'enrich_alert',
  'investigate_alert',
  'determine_response',
  'execute_response',
  'handle_error',
  'end'
];

const PipelineFlowVisualization = ({ pipelineState }) => {
  // Generate nodes and edges based on pipeline state
  const { nodes, edges } = useMemo(() => {
    const currentStep = pipelineState?.current_step || null;
    const errorStep = pipelineState?.error_message ? pipelineState.current_step : null;
    
    // Create nodes for each pipeline step
    const nodes = PIPELINE_STEPS.map((step, index) => {
      // Determine node status based on current state
      let status = 'pending';
      
      if (errorStep && step === errorStep) {
        status = 'error';
      } else if (step === currentStep) {
        status = 'active';
      } else if (currentStep) {
        // Check if this step has been completed based on pipeline progression
        const currentStepIndex = PIPELINE_STEPS.indexOf(currentStep);
        if (index < currentStepIndex) {
          status = 'completed';
        }
      }
      
      // Handle special case for end node
      if (step === 'end' && pipelineState?.status === 'COMPLETED') {
        status = 'completed';
      }
      
      // Format step name for display
      const label = step
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
      
      return {
        id: step,
        type: 'pipelineStep',
        position: { x: 100 + index * 200, y: 100 },
        data: { 
          label, 
          status,
          step,
          error: step === errorStep ? pipelineState.error_message : null
        }
      };
    });
    
    // Create edges connecting the steps
    const edges = PIPELINE_STEPS.slice(0, -1).map((step, index) => ({
      id: `${step}-to-${PIPELINE_STEPS[index + 1]}`,
      source: step,
      target: PIPELINE_STEPS[index + 1],
      type: 'smoothstep',
      animated: step === currentStep,
      markerEnd: {
        type: MarkerType.ArrowClosed,
      },
      style: { 
        strokeWidth: 2, 
        stroke: step === errorStep ? '#e53e3e' : '#3182ce' 
      }
    }));
    
    // Add error edge if applicable
    if (errorStep && errorStep !== 'handle_error') {
      edges.push({
        id: `${errorStep}-to-error`,
        source: errorStep,
        target: 'handle_error',
        type: 'smoothstep',
        animated: true,
        style: { strokeWidth: 2, stroke: '#e53e3e' },
        markerEnd: {
          type: MarkerType.ArrowClosed,
        },
      });
    }
    
    return { nodes, edges };
  }, [pipelineState]);

  return (
    <div style={{ height: 180 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.5}
        maxZoom={1.5}
        defaultViewport={{ x: 0, y: 0, zoom: 0.7 }}
      >
        <Background color="#2d3748" gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
};

export default PipelineFlowVisualization;
