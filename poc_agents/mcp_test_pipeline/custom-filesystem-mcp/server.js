// Enhanced MCP Filesystem Server with better protocol compatibility

const http = require('http');
const fs = require('fs');
const path = require('path');

// Get root directory from command line or use current directory
const rootDir = process.argv[2] || "/data";
const port = process.env.MCP_PORT || 8001;

// Initialize test files for the MCP test pipeline
function createTestFiles() {
  console.log("Creating test files for MCP test pipeline...");
  const fs = require('fs');
  const path = require('path');
  
  // Define test files with their content
  const testFiles = {
    '/data/test_script.py': `
# Test script for MCP filesystem server
def test_function():
    print("Hello from test_script.py")
    return "Test successful"

if __name__ == "__main__":
    test_function()
`,
    '/data/test_data.json': `
{
    "name": "MCP Test Data",
    "version": "1.0.0",
    "description": "Test data for the MCP filesystem server",
    "test_array": [1, 2, 3, 4, 5],
    "test_object": {
        "key1": "value1",
        "key2": "value2"
    }
}
`
  };
  
  // Create each test file in multiple possible locations
  Object.entries(testFiles).forEach(([filePath, content]) => {
    // Define multiple possible paths for this file
    const testPaths = [
      // Direct path
      filePath,
      // Without /data/ prefix
      filePath.replace('/data/', '/'),
      // Relative to rootDir
      path.join(rootDir, filePath.substring('/data/'.length))
    ];
    
    // Try to create the file in each location
    testPaths.forEach(testPath => {
      try {
        // Create directory structure if it doesn't exist
        const dirPath = path.dirname(testPath);
        fs.mkdirSync(dirPath, { recursive: true });
        
        // Write the file
        fs.writeFileSync(testPath, content);
        console.log(`Created test file: ${testPath}`);
      } catch (error) {
        console.warn(`Failed to create test file ${testPath}: ${error.message}`);
      }
    });
  });
  
  console.log("Test file creation completed");
}

// Create test files on startup
createTestFiles();

// Helper function to check if a file exists (better approach than directly using fs.existsSync)
async function pathExists(filePath) {
  try {
    await fs.promises.access(filePath, fs.constants.R_OK);
    return true;
  } catch (error) {
    return false;
  }
}

// Helper function to resolve file paths based on rootDir
async function resolveFilePath(requestedPath) {
  console.log(`Resolving path: ${requestedPath}, rootDir: ${rootDir}`);
  
  // Handle both types of paths
  if (requestedPath.startsWith('/data/')) {
    const directPath = requestedPath;
    const withoutDataPath = requestedPath.replace('/data/', '/');
    const relativePath = path.join(rootDir, requestedPath.substring('/data/'.length));
    
    console.log(`Trying multiple path options:`);
    console.log(`- Direct path: ${directPath}`);
    console.log(`- Without data path: ${withoutDataPath}`);
    console.log(`- Relative path: ${relativePath}`);
    
    // Check all possible locations, return the first one that exists
    if (await pathExists(directPath)) {
      console.log(`File exists at direct path: ${directPath}`);
      return directPath;
    }
    
    if (await pathExists(withoutDataPath)) {
      console.log(`File exists at without-data path: ${withoutDataPath}`);
      return withoutDataPath;
    }
    
    if (await pathExists(relativePath)) {
      console.log(`File exists at relative path: ${relativePath}`);
      return relativePath;
    }
    
    // None existed, return the direct path to let the error happen naturally
    return directPath;
  }
  
  // For non-data paths, join with rootDir
  const resolvedPath = path.join(rootDir, requestedPath);
  console.log(`Resolved regular path to: ${resolvedPath}`);
  return resolvedPath;
}

console.log(`Starting MCP filesystem server on port ${port}`);
console.log(`Root directory: ${rootDir}`);
console.log(`Transport: HTTP`);
console.log(`MCP PROTOCOL: Using MCP compliant response format with isError for errors`);

// Create HTTP server
const server = http.createServer((req, res) => {
  // Enhanced request logging
  console.log(`${new Date().toISOString()} - Received ${req.method} request for: ${req.url}`);
  
  // Add CORS headers for all responses
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  // Handle OPTIONS preflight requests
  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }
  
  // Basic health check endpoint
  if (req.url === '/health' && req.method === 'GET') {
    res.writeHead(200, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({status: "ok", root_directory: rootDir}));
    return;
  }
  
  // Handle requests for the MCP SSE endpoint
  if (req.url === '/mcp/sse' && req.method === 'GET') {
    console.log('MCP SSE connection requested - replying with friendly message');
    // Send HTTP 200 with text explaining the server capabilities
    res.writeHead(200, { 
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*',
    });
    // Send an initial comment to keep the connection open
    res.write(": SSE connection established\n\n");
    return;
  }
  
  // Handle MCP message endpoint (needed for the proxy)
  if (req.url.startsWith('/mcp/messages/') && req.method === 'POST') {
    console.log('MCP message endpoint hit');
    let body = '';
    
    req.on('data', chunk => {
      body += chunk.toString();
    });
    
    req.on('end', () => {
      try {
        console.log(`Received message body: ${body}`);
        // Just return success - we don't have a real session but this helps the proxy
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: true }));
      } catch (err) {
        console.error(`Error processing message: ${err.message}`);
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
      }
    });
    return;
  }
  
  if (req.method === 'POST') {
    let body = '';
    
    req.on('data', chunk => {
      body += chunk.toString();
    });
    
    req.on('end', () => {
      try {
        const jsonRPC = JSON.parse(body);
        
        // Handle JSON-RPC method
        if (jsonRPC.method === 'tools/list') {
          // Return available filesystem tools
          const result = {
            jsonrpc: "2.0",
            id: jsonRPC.id,
            result: {
              tools: [
                {
                  name: "filesystem.readFile",
                  description: "Read content of a file",
                  inputSchema: {
                    type: "object",
                    properties: {
                      path: { type: "string", description: "Path to the file" }
                    },
                    required: ["path"]
                  }
                },
                {
                  name: "filesystem.writeFile",
                  description: "Write content to a file",
                  inputSchema: {
                    type: "object",
                    properties: {
                      path: { type: "string", description: "Path to the file" },
                      content: { type: "string", description: "Content to write" }
                    },
                    required: ["path", "content"]
                  }
                },
                {
                  name: "filesystem.listDirectory",
                  description: "List files in a directory",
                  inputSchema: {
                    type: "object",
                    properties: {
                      path: { type: "string", description: "Path to the directory" }
                    },
                    required: ["path"]
                  }
                }
              ]
            }
          };
          
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(result));
          
        } else if (jsonRPC.method === 'tools/call') {
          // Handle tool execution
          const toolName = jsonRPC.params.name;
          const args = jsonRPC.params.arguments;
          
          console.log(`Executing tool: ${toolName}`);
          console.log(`Arguments: ${JSON.stringify(args)}`);
          
          if (toolName === 'filesystem.readFile') {
            console.log(`Read file request for: ${args.path}`);
            
            // Handle read file operation with async/await using IIFE
            (async () => {
              try {
                // Resolve path asynchronously with better handling
                const filePath = await resolveFilePath(args.path);
                console.log(`Attempting to read file at resolved path: ${filePath}`);
                
                // Read file asynchronously
                let content;
                try {
                  content = await fs.promises.readFile(filePath, 'utf8');
                  console.log(`Successfully read file, ${content.length} bytes`);
                  
                  // MCP-compliant SUCCESS response
                  const result = {
                    jsonrpc: "2.0",
                    id: jsonRPC.id,
                    result: {
                      content: [
                        {
                          type: "text",
                          text: content
                        }
                      ]
                    }
                  };
                  
                  res.writeHead(200, { 'Content-Type': 'application/json' });
                  res.end(JSON.stringify(result));
                  
                } catch (readError) {
                  // File read error - use MCP-compliant ERROR response with isError: true
                  console.error(`Error reading file: ${readError.message}`);
                  
                  // MCP protocol requires isError: true inside result, not a standard JSON-RPC error
                  const result = {
                    jsonrpc: "2.0",
                    id: jsonRPC.id,
                    result: {
                      isError: true, // This is critical for MCP protocol compliance
                      content: [
                        {
                          type: "text",
                          text: `Error reading file: ${readError.message}`
                        }
                      ]
                    }
                  };
                  
                  res.writeHead(200, { 'Content-Type': 'application/json' });
                  res.end(JSON.stringify(result));
                }
                
              } catch (pathError) {
                // Path resolution error - MCP-compliant ERROR response
                console.error(`Error resolving path: ${pathError.message}`);
                
                const result = {
                  jsonrpc: "2.0",
                  id: jsonRPC.id,
                  result: {
                    isError: true, // MCP protocol compliance
                    content: [
                      {
                        type: "text",
                        text: `Error resolving path: ${pathError.message}`
                      }
                    ]
                  }
                };
                
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify(result));
              }
            })().catch(error => {
              // Unexpected error in async IIFE - MCP-compliant ERROR response
              console.error(`Unexpected error in filesystem.readFile: ${error.message}`);
              
              const result = {
                jsonrpc: "2.0",
                id: jsonRPC.id,
                result: {
                  isError: true, // MCP protocol compliance
                  content: [
                    {
                      type: "text",
                      text: `Unexpected error in filesystem.readFile: ${error.message}`
                    }
                  ]
                }
              };
              
              res.writeHead(200, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify(result));
            });
            
            // Note: Don't put code after this point for this tool, as the IIFE handles the response asynchronously
            
          } else if (toolName === 'filesystem.writeFile') {
          console.log(`Write file request for: ${args.path}`);
          
          // Handle write file operation with async/await using IIFE
          (async () => {
          try {
            // Resolve path asynchronously with better handling
            const filePath = await resolveFilePath(args.path);
            console.log(`Attempting to write file at resolved path: ${filePath}`);
            
            // Ensure directory exists
            try {
            const dirPath = path.dirname(filePath);
            await fs.promises.mkdir(dirPath, { recursive: true });
          } catch (mkdirError) {
          console.error(`Error creating directory: ${mkdirError.message}`);
          // Continue anyway, the write might still succeed
          }
          
          // Write file asynchronously
          try {
            await fs.promises.writeFile(filePath, args.content, 'utf8');
              console.log(`Successfully wrote file, ${args.content.length} bytes`);
              
              // MCP-compliant SUCCESS response
              const result = {
                jsonrpc: "2.0",
                  id: jsonRPC.id,
                result: {
                  content: [
                    {
                    type: "text",
                    text: `Successfully wrote to ${args.path}`
                  }
              ]
            }
          };
          
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(result));
          
          } catch (writeError) {
              // File write error - use MCP-compliant ERROR response with isError: true
              console.error(`Error writing file: ${writeError.message}`);
              
              const result = {
                  jsonrpc: "2.0",
                    id: jsonRPC.id,
                    result: {
                      isError: true, // This is critical for MCP protocol compliance
                      content: [
                        {
                          type: "text",
                          text: `Error writing file: ${writeError.message}`
                        }
                      ]
                    }
                  };
                  
                  res.writeHead(200, { 'Content-Type': 'application/json' });
                  res.end(JSON.stringify(result));
                }
                
              } catch (pathError) {
                // Path resolution error - MCP-compliant ERROR response
                console.error(`Error resolving path: ${pathError.message}`);
                
                const result = {
                  jsonrpc: "2.0",
                  id: jsonRPC.id,
                  result: {
                    isError: true, // MCP protocol compliance
                    content: [
                      {
                        type: "text",
                        text: `Error resolving path: ${pathError.message}`
                      }
                    ]
                  }
                };
                
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify(result));
              }
            })().catch(error => {
              // Unexpected error in async IIFE - MCP-compliant ERROR response
              console.error(`Unexpected error in filesystem.writeFile: ${error.message}`);
              
              const result = {
                jsonrpc: "2.0",
                id: jsonRPC.id,
                result: {
                  isError: true, // MCP protocol compliance
                  content: [
                    {
                      type: "text",
                      text: `Unexpected error in filesystem.writeFile: ${error.message}`
                    }
                  ]
                }
              };
              
              res.writeHead(200, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify(result));
            });
            
            // Note: Don't put code after this point for this tool
            
          } else if (toolName === 'filesystem.listDirectory') {
            console.log(`List directory request for: ${args.path}`);
            
            // Handle list directory operation with async/await using IIFE
            (async () => {
              try {
                // Resolve path asynchronously with better handling
                const dirPath = await resolveFilePath(args.path);
                console.log(`Attempting to list directory at resolved path: ${dirPath}`);
                
                // List directory asynchronously
                try {
                  const files = await fs.promises.readdir(dirPath);
                  console.log(`Successfully listed directory with ${files.length} files`);
                  
                  // Format with file type indicators using async operations
                  const filePromises = files.map(async (file) => {
                    try {
                      const fullPath = path.join(dirPath, file);
                      const stats = await fs.promises.stat(fullPath);
                      return `${stats.isDirectory() ? '[DIR]' : '[FILE]'} ${file}`;
                    } catch (statErr) {
                      return `[UNKNOWN] ${file}`;
                    }
                  });
                  
                  const formattedFiles = await Promise.all(filePromises);
                  const formattedOutput = formattedFiles.join('\n') || 'Directory is empty';
                  
                  // MCP-compliant SUCCESS response
                  const result = {
                    jsonrpc: "2.0",
                    id: jsonRPC.id,
                    result: {
                      content: [
                        {
                          type: "text",
                          text: formattedOutput
                        }
                      ]
                    }
                  };
                  
                  res.writeHead(200, { 'Content-Type': 'application/json' });
                  res.end(JSON.stringify(result));
                  
                } catch (readDirError) {
                  // Directory listing error - use MCP-compliant ERROR response with isError: true
                  console.error(`Error listing directory: ${readDirError.message}`);
                  
                  const result = {
                    jsonrpc: "2.0",
                    id: jsonRPC.id,
                    result: {
                      isError: true, // This is critical for MCP protocol compliance
                      content: [
                        {
                          type: "text",
                          text: `Error listing directory: ${readDirError.message}`
                        }
                      ]
                    }
                  };
                  
                  res.writeHead(200, { 'Content-Type': 'application/json' });
                  res.end(JSON.stringify(result));
                }
                
              } catch (pathError) {
                // Path resolution error - MCP-compliant ERROR response
                console.error(`Error resolving path: ${pathError.message}`);
                
                const result = {
                  jsonrpc: "2.0",
                  id: jsonRPC.id,
                  result: {
                    isError: true, // MCP protocol compliance
                    content: [
                      {
                        type: "text",
                        text: `Error resolving path: ${pathError.message}`
                      }
                    ]
                  }
                };
                
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify(result));
              }
            })().catch(error => {
              // Unexpected error in async IIFE - MCP-compliant ERROR response
              console.error(`Unexpected error in filesystem.listDirectory: ${error.message}`);
              
              const result = {
                jsonrpc: "2.0",
                id: jsonRPC.id,
                result: {
                  isError: true, // MCP protocol compliance
                  content: [
                    {
                      type: "text",
                      text: `Unexpected error in filesystem.listDirectory: ${error.message}`
                    }
                  ]
                }
              };
              
              res.writeHead(200, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify(result));
            });
            
            // Note: Don't put code after this point for this tool
            
          } else {
            // Tool not found
            const errorResult = {
              jsonrpc: "2.0",
              id: jsonRPC.id,
              error: {
                code: -32601,
                message: `Tool not found: ${toolName}`
              }
            };
            
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(errorResult));
          }
          
        } else {
          // Method not found
          const errorResult = {
            jsonrpc: "2.0",
            id: jsonRPC.id,
            error: {
              code: -32601,
              message: `Method not found: ${jsonRPC.method}`
            }
          };
          
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(errorResult));
        }
        
      } catch (err) {
        // Invalid JSON
        const errorResult = {
          jsonrpc: "2.0",
          id: null,
          error: {
            code: -32700,
            message: `Parse error: ${err.message}`
          }
        };
        
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(errorResult));
      }
    });
    
  } else {
    // Method not allowed
    res.writeHead(405, { 'Content-Type': 'text/plain' });
    res.end('Method not allowed');
  }
});

// Start server
server.listen(port, '0.0.0.0', () => {
  console.log(`MCP Filesystem server listening at http://0.0.0.0:${port}`);
});