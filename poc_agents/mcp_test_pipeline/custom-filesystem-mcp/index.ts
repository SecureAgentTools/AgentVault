#!/usr/bin/env node

import { createServer, FilesystemServerOptions } from "@modelcontextprotocol/sdk";
import * as fs from "fs";
import * as path from "path";

// Get the path from command line args or default to current directory
const targetPath = process.argv[2] || ".";

// Check if path exists
if (!fs.existsSync(targetPath)) {
  console.error(`Error: Path "${targetPath}" does not exist.`);
  process.exit(1);
}

// Configuration from environment variables
const port = process.env.MCP_PORT ? parseInt(process.env.MCP_PORT, 10) : 8001;
const transport = process.env.MCP_TRANSPORT || "stdio";
const fsRoot = process.env.MCP_FS_ROOT || targetPath;
const readOnly = process.env.MCP_FS_READ_ONLY === "true";

// Server options
const options: FilesystemServerOptions = {
  root: fsRoot,
  readOnly: readOnly,
  transport: transport as "stdio" | "http",
  port: port
};

// Log configuration
console.log(`Starting MCP Filesystem Server with configuration:`);
console.log(`- Transport: ${options.transport}`);
console.log(`- Port (if HTTP): ${options.port}`);
console.log(`- Root directory: ${options.root}`);
console.log(`- Read-only mode: ${options.readOnly}`);

// Create and start the server
try {
  createServer(options);
  console.log(`Server started successfully`);
} catch (error) {
  console.error(`Failed to start server:`, error);
  process.exit(1);
}