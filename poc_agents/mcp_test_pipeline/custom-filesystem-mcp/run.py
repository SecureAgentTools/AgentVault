#!/usr/bin/env python3
"""
Improved script to run the custom-filesystem-mcp server
This properly handles Python module imports
"""
import os
import sys
import logging
import uvicorn

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("custom-filesystem-mcp")
    
    # Get the absolute path to the project root
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    # Add both the project root and src directory to Python path
    sys.path.insert(0, project_root)
    sys.path.insert(0, os.path.join(project_root, 'src'))
    
    # Log the Python path for debugging
    logger.debug(f"PYTHONPATH: {os.environ.get('PYTHONPATH', '')}")
    logger.debug(f"sys.path: {sys.path}")
    
    # Run the uvicorn server with the correct module path
    logger.info("Starting uvicorn server...")
    try:
        import src.custom_filesystem_mcp.main
        logger.info("Module imported successfully")
        
        uvicorn.run(
            "src.custom_filesystem_mcp.main:app",
            host="0.0.0.0",
            port=8001,
            log_level="debug"
        )
    except ImportError as e:
        logger.error(f"Failed to import module: {e}")
        logger.error("Attempting alternate import path...")
        
        try:
            # Try alternate import path if the first one fails
            import custom_filesystem_mcp.main
            logger.info("Module imported successfully with alternate path")
            
            uvicorn.run(
                "custom_filesystem_mcp.main:app",
                host="0.0.0.0",
                port=8001,
                log_level="debug"
            )
        except ImportError as e2:
            logger.critical(f"All import attempts failed: {e2}")
            sys.exit(1)
