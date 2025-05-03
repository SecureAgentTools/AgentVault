import logging
import asyncio
import json
import random
# --- ADDED: Import List ---
from typing import Dict, Any, Union, List
# --- END ADDED ---
import datetime # Added for timestamp

# Import base class and SDK components
from base_agent import ResearchAgent
from agentvault_server_sdk.state import TaskState
from agentvault_server_sdk.exceptions import AgentProcessingError

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in visualization_agent. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState # Use state from base if possible
    _MODELS_AVAILABLE = False


logger = logging.getLogger(__name__)

AGENT_ID = "visualization-agent"

class VisualizationAgent(ResearchAgent):
    """
    Identifies data suitable for visualization and generates charts/graphs.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Visualization Agent"})

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Processes verified facts or other structured data to generate visualizations.
        Expects 'content' to be a dictionary containing the 'verified_facts' artifact content.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Processing visualization request for task {task_id}")

        try:
            # Enable debug logging to track the structure
            self.logger.debug(f"Content received: {json.dumps(content, indent=2)[:500]}...")
            
            # Ensure all RPC parameter names are consistent (id vs taskId)
            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            # --- IMPROVED: More robust fact extraction from different structures ---
            # Try to find facts in various possible locations in the content
            verified_facts = []
            
            # Try the standard structure first
            verified_facts_artifact_content = content.get("verified_facts", {})
            if isinstance(verified_facts_artifact_content, dict) and "verified_facts" in verified_facts_artifact_content:
                verified_facts = verified_facts_artifact_content.get("verified_facts", [])
            elif isinstance(verified_facts_artifact_content, list):
                verified_facts = verified_facts_artifact_content
            
            # If not found, try other common structures
            if not verified_facts:
                # Try direct facts key
                if "facts" in content:
                    verified_facts = content["facts"]
                # Try extracted_information structure
                elif "extracted_information" in content:
                    extracted_info = content["extracted_information"]
                    if isinstance(extracted_info, dict) and "extracted_facts" in extracted_info:
                        verified_facts = extracted_info["extracted_facts"]
                # Look for any list of dictionaries that might be facts
                for key, value in content.items():
                    if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                        verified_facts = value
                        break
            
            # Create placeholders even when no verified facts
            if not verified_facts:
                self.logger.warning(f"Task {task_id}: No verified facts found in input. Creating placeholder visualization.")
                # Instead of exiting, create sample visualization
                generated_visualizations = []
                viz_metadata_list = []
                
                # Generate a minimal placeholder visualization
                viz_id = f"viz-{task_id}-placeholder"
                chart_type = "placeholder_chart"
                dummy_svg_content = f'<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f0f0f0"/><text x="10" y="50" fill="#333">Sample visualization - No data available</text></svg>'
                
                generated_visualizations.append({
                    "id": viz_id,
                    "type": chart_type,
                    "content": dummy_svg_content,
                    "media_type": "image/svg+xml",
                    "description": "Placeholder visualization created when no data was available."
                })
                
                viz_metadata_list.append({
                    "visualization_id": viz_id,
                    "chart_type": chart_type,
                    "related_content_ids": []
                })
                
                # Create and send artifact
                if _MODELS_AVAILABLE:
                    viz_artifact = Artifact(
                        id=viz_id,
                        type=chart_type,
                        content=dummy_svg_content,
                        media_type="image/svg+xml",
                        metadata={"description": "Placeholder visualization"}
                    )
                    await self.task_store.notify_artifact_event(task_id, viz_artifact)
                    
                    # Visualization Metadata Artifact
                    viz_meta_artifact = Artifact(
                        id=f"{task_id}-viz_metadata", 
                        type="viz_metadata",
                        content={"visualizations": viz_metadata_list}, 
                        media_type="application/json"
                    )
                    await self.task_store.notify_artifact_event(task_id, viz_meta_artifact)
                
                # Notify completion
                completion_message = "Generated placeholder visualization due to lack of input data."
                if _MODELS_AVAILABLE:
                    response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                    await self.task_store.notify_message_event(task_id, response_msg)
                
                # Complete the task
                await self.task_store.update_task_state(task_id, TaskState.COMPLETED)
                return

            self.logger.info(f"Task {task_id}: Analyzing {len(verified_facts)} facts for visualization potential.")

            # --- Actual Visualization Logic ---
            generated_visualizations = []
            viz_metadata_list = []
            
            # Helper function to create SVG bar chart
            def create_bar_chart(title, data_points, width=500, height=300, max_bars=8):
                # Limit to max_bars and sort by value for better visualization
                sorted_data = sorted(data_points, key=lambda x: x["value"], reverse=True)[:max_bars]
                
                # Calculate dimensions
                margin = 50  # margins for labels
                chart_width = width - 2 * margin
                chart_height = height - 2 * margin
                bar_spacing = 10
                bar_width = (chart_width / len(sorted_data)) - bar_spacing if sorted_data else 0
                
                # Find maximum value for scaling
                max_value = max([point["value"] for point in sorted_data]) if sorted_data else 1
                
                # Create SVG header
                svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">' 
                
                # Add title
                svg += f'<text x="{width/2}" y="20" text-anchor="middle" font-family="sans-serif" font-size="16" font-weight="bold">{title}</text>'
                
                # Add Y-axis line
                svg += f'<line x1="{margin}" y1="{height-margin}" x2="{margin}" y2="{margin}" stroke="black" stroke-width="1"/>'
                
                # Add X-axis line
                svg += f'<line x1="{margin}" y1="{height-margin}" x2="{width-margin}" y2="{height-margin}" stroke="black" stroke-width="1"/>'
                
                # Create colored bars with labels
                colors = ["#4285F4", "#DB4437", "#F4B400", "#0F9D58", "#9C27B0", "#FF6D00", "#00ACC1", "#9E9E9E"]
                
                for i, point in enumerate(sorted_data):
                    # Calculate bar position and height
                    bar_height = (point["value"] / max_value) * chart_height
                    x = margin + i * (bar_width + bar_spacing)
                    y = height - margin - bar_height
                    color = colors[i % len(colors)]
                    
                    # Add bar
                    svg += f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" fill="{color}" />'
                    
                    # Add value label on top of bar
                    svg += f'<text x="{x + bar_width/2}" y="{y - 5}" text-anchor="middle" font-family="sans-serif" font-size="12">{point["value"]}</text>'
                    
                    # Add x-axis label (vertical for long labels)
                    label = point["label"][:10] + '...' if len(point["label"]) > 10 else point["label"]
                    svg += f'<text x="{x + bar_width/2}" y="{height-margin+15}" transform="rotate(45, {x + bar_width/2}, {height-margin+15})" text-anchor="start" font-family="sans-serif" font-size="10">{label}</text>'
                
                # Close SVG
                svg += '</svg>'
                return svg
            
            # Helper function to create pie chart
            def create_pie_chart(title, data_points, width=400, height=400, max_segments=6):
                # Limit to max_segments and sort by value
                sorted_data = sorted(data_points, key=lambda x: x["value"], reverse=True)[:max_segments]
                
                # Calculate dimensions
                cx = width / 2  # center x
                cy = height / 2  # center y
                radius = min(cx, cy) - 50  # radius with margin
                
                # Calculate total for percentages
                total = sum([point["value"] for point in sorted_data])
                if total == 0:
                    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><text x="10" y="20" font-family="sans-serif">No data available for pie chart</text></svg>'
                
                # Create SVG header
                svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">' 
                
                # Add title
                svg += f'<text x="{width/2}" y="20" text-anchor="middle" font-family="sans-serif" font-size="16" font-weight="bold">{title}</text>'
                
                # Colors for segments
                colors = ["#4285F4", "#DB4437", "#F4B400", "#0F9D58", "#9C27B0", "#FF6D00", "#00ACC1", "#9E9E9E"]
                
                # Draw pie segments
                start_angle = 0
                legend_y = 40
                
                for i, point in enumerate(sorted_data):
                    # Calculate angles
                    angle = (point["value"] / total) * 360
                    end_angle = start_angle + angle
                    
                    # Convert to radians for sin/cos
                    start_rad = start_angle * (3.141592653589793 / 180)
                    end_rad = end_angle * (3.141592653589793 / 180)
                    
                    # Calculate points
                    x1 = cx + radius * (0 if angle >= 180 else 1)
                    y1 = cy
                    x2 = cx + radius * 0.999 * (0 if angle >= 180 else 1)  # slightly smaller to avoid overlap
                    y2 = cy
                    
                    # For angles < 180, we can use a simple arc
                    large_arc = 1 if angle > 180 else 0
                    
                    # Starting point
                    start_x = cx + (radius * 0.999 * 0)
                    start_y = cy
                    
                    # End point
                    end_x = cx + (radius * 0.999 * 0)
                    end_y = cy
                    
                    if start_angle > 0:
                        start_x = cx + (radius * 0.999 * 1)
                        start_y = cy
                    
                    if end_angle > 0 and end_angle < 360:
                        end_x = cx + (radius * 0.999 * 1)
                        end_y = cy
                    
                    # Create path for segment
                    color = colors[i % len(colors)]
                    percent = round((point["value"] / total) * 100, 1)
                    
                    # Simple rectangular segment as placeholder (actual pie chart would need more math)
                    segment_height = radius * (point["value"] / total) * 1.8
                    segment_y = cy - segment_height/2 + (i * 10)
                    svg += f'<rect x="{cx-radius/2}" y="{segment_y}" width="{radius}" height="{segment_height}" fill="{color}" />' 
                    
                    # Add legend item
                    legend_x = width - radius - 20
                    svg += f'<rect x="{legend_x}" y="{legend_y}" width="10" height="10" fill="{color}" />'
                    svg += f'<text x="{legend_x + 15}" y="{legend_y + 9}" font-family="sans-serif" font-size="12">{point["label"]} ({percent}%)</text>'
                    legend_y += 20
                    
                    # Update for next segment
                    start_angle = end_angle
                
                # Close SVG
                svg += '</svg>'
                return svg
            
            # Sort facts by categories and confidence
            categories = {}
            subtopics = {}
            confidence_counts = {"high": 0, "medium": 0, "low": 0}
            
            # Process facts to extract visualization data
            for fact in verified_facts:
                # Get fact details
                fact_id = fact.get("id", str(random.randint(1000, 9999)))
                verification_status = fact.get("verification_status", "")
                confidence_score = fact.get("confidence_score", 0.5)
                subtopic = fact.get("subtopic", "General")
                text = fact.get("text", "")
                source_url = fact.get("source_url", "")
                
                # Track verification status
                if verification_status not in categories:
                    categories[verification_status] = 0
                categories[verification_status] += 1
                
                # Track subtopics
                if subtopic not in subtopics:
                    subtopics[subtopic] = 0
                subtopics[subtopic] += 1
                
                # Track confidence levels
                if confidence_score >= 0.75:
                    confidence_counts["high"] += 1
                elif confidence_score >= 0.4:
                    confidence_counts["medium"] += 1
                else:
                    confidence_counts["low"] += 1
            
            # Create visualizations based on the data collected
            visualizations_to_create = []
            
            # 1. Verification Status Bar Chart
            if categories:
                visualizations_to_create.append({
                    "title": "Facts by Verification Status",
                    "type": "bar_chart",
                    "data": [{'label': status, 'value': count} for status, count in categories.items()]
                })
            
            # 2. Confidence Level Pie Chart
            if sum(confidence_counts.values()) > 0:
                visualizations_to_create.append({
                    "title": "Facts by Confidence Level",
                    "type": "pie_chart",
                    "data": [{'label': level, 'value': count} for level, count in confidence_counts.items()]
                })
            
            # 3. Subtopics Bar Chart (if we have enough different subtopics)
            if len(subtopics) > 1:
                visualizations_to_create.append({
                    "title": "Facts by Subtopic",
                    "type": "bar_chart",
                    "data": [{'label': subtopic, 'value': count} for subtopic, count in subtopics.items()]
                })
            
            # Generate the visualizations
            for i, viz_data in enumerate(visualizations_to_create):
                viz_id = f"viz-{task_id}-{i}"
                chart_type = viz_data["type"]
                title = viz_data["title"]
                data_points = viz_data["data"]
                
                # Generate the SVG content based on chart type
                svg_content = ""
                if chart_type == "bar_chart":
                    svg_content = create_bar_chart(title, data_points)
                elif chart_type == "pie_chart":
                    svg_content = create_pie_chart(title, data_points)
                else:
                    # Fallback for unknown chart types
                    svg_content = f'<svg width="200" height="100"><text x="10" y="20">Unsupported chart type: {chart_type}</text></svg>'
                
                # Add to generated visualizations
                generated_visualizations.append({
                    "id": viz_id,
                    "type": chart_type,
                    "content": svg_content,
                    "media_type": "image/svg+xml",
                    "description": f"{title} - A {chart_type} visualization of verified facts."
                })
                
                # Create metadata for this visualization
                # Find related facts based on the visualization type
                related_fact_ids = []
                
                if chart_type == "bar_chart" and title == "Facts by Verification Status":
                    # Include facts with the highest count status
                    top_status = max(categories.items(), key=lambda x: x[1])[0] if categories else None
                    if top_status:
                        related_fact_ids = [f.get("id") for f in verified_facts 
                                           if f.get("verification_status") == top_status 
                                           and f.get("id") is not None][:5]  # limit to 5
                
                elif chart_type == "pie_chart" and title == "Facts by Confidence Level":
                    # Include high confidence facts
                    related_fact_ids = [f.get("id") for f in verified_facts 
                                       if f.get("confidence_score", 0) >= 0.75 
                                       and f.get("id") is not None][:5]  # limit to 5
                
                elif chart_type == "bar_chart" and title == "Facts by Subtopic":
                    # Include facts from the largest subtopic
                    top_subtopic = max(subtopics.items(), key=lambda x: x[1])[0] if subtopics else None
                    if top_subtopic:
                        related_fact_ids = [f.get("id") for f in verified_facts 
                                           if f.get("subtopic") == top_subtopic 
                                           and f.get("id") is not None][:5]  # limit to 5
                
                viz_metadata_list.append({
                    "visualization_id": viz_id,
                    "chart_type": chart_type,
                    "title": title,
                    "related_content_ids": related_fact_ids
                })
            
            # If no visualizations were created, add a placeholder
            if not generated_visualizations:
                viz_id = f"viz-{task_id}-placeholder"
                chart_type = "info_graphic"
                svg_content = f'''
                <svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">
                    <rect width="100%" height="100%" fill="#f0f0f0" />
                    <text x="50%" y="40%" text-anchor="middle" font-family="sans-serif" font-size="16">No suitable data found for visualization</text>
                    <text x="50%" y="60%" text-anchor="middle" font-family="sans-serif" font-size="14">Processed {len(verified_facts)} facts</text>
                </svg>
                '''
                
                generated_visualizations.append({
                    "id": viz_id,
                    "type": chart_type,
                    "content": svg_content,
                    "media_type": "image/svg+xml",
                    "description": "No data suitable for visualization was found."
                })
                
                viz_metadata_list.append({
                    "visualization_id": viz_id,
                    "chart_type": chart_type,
                    "title": "No Suitable Data for Visualization",
                    "related_content_ids": []
                })
            
            # --- End Visualization Logic ---

            # Notify artifacts
            if _MODELS_AVAILABLE:
                # Create individual artifacts for each visualization
                for viz_data in generated_visualizations:
                    viz_artifact = Artifact(
                        id=viz_data["id"],
                        type=viz_data["type"],
                        content=viz_data["content"],
                        media_type=viz_data["media_type"],
                        # url=viz_data.get("url"), # Use if URL is generated
                        metadata={"description": viz_data["description"]}
                    )
                    await self.task_store.notify_artifact_event(task_id, viz_artifact)

                # Visualization Metadata Artifact (mapping visualizations to content)
                viz_meta_artifact = Artifact(
                    id=f"{task_id}-viz_metadata", type="viz_metadata",
                    content={"visualizations": viz_metadata_list}, media_type="application/json"
                )
                await self.task_store.notify_artifact_event(task_id, viz_meta_artifact)
            else:
                logger.warning("Cannot notify artifacts: Core models not available.")


            # Notify completion message
            completion_message = f"Generated {len(generated_visualizations)} dummy visualizations."
            if _MODELS_AVAILABLE:
                 response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)])
                 await self.task_store.notify_message_event(task_id, response_msg)
            else:
                 logger.info(completion_message)

            await self.task_store.update_task_state(task_id, TaskState.COMPLETED)
            self.logger.info(f"Successfully processed visualization request for task {task_id}")

        except Exception as e:
            self.logger.exception(f"Error processing visualization request for task {task_id}: {e}")
            error_message = f"Failed to process visualization request: {e}"
            await self.task_store.update_task_state(task_id, TaskState.FAILED, message=error_message)
            if _MODELS_AVAILABLE:
                 error_msg_obj = Message(role="assistant", parts=[TextPart(content=error_message)])
                 await self.task_store.notify_message_event(task_id, error_msg_obj)


# FastAPI app setup
from fastapi import FastAPI, Depends, BackgroundTasks # Added imports
from fastapi.middleware.cors import CORSMiddleware
from agentvault_server_sdk import create_a2a_router
import os

# Create agent instance
agent = VisualizationAgent()

# Create FastAPI app
app = FastAPI(title="VisualizationAgent")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include A2A router with BackgroundTasks dependency
router = create_a2a_router(
    agent=agent,
    task_store=agent.task_store, # Pass the agent's store
    dependencies=[Depends(lambda: BackgroundTasks())] # Add dependency here
)
app.include_router(router, prefix="/a2a")


# Serve agent card
@app.get("/agent-card.json")
async def get_agent_card():
    card_path = os.getenv("AGENT_CARD_PATH", "/app/agent-card.json")
    try:
        with open(card_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read agent card from {card_path}: {e}")
        # Fallback - try to read from mounted location
        try:
            with open("/app/agent-card.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e2:
            logger.error(f"Failed to read fallback agent card: {e2}")
            return {"error": "Agent card not found"}

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
