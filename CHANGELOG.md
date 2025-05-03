# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-05-02

### Overview

This is the first major release of AgentVault, marking the project as production-ready. All core components have been thoroughly tested and are ready for deployment.

### Components

- **agentvault** (Library): 1.0.0 - Core Python client library for A2A protocol
- **agentvault-cli**: 1.0.0 - Command-line interface for AgentVault
- **agentvault-registry-api**: 1.0.0 - Central registry API service
- **agentvault-server-sdk**: 1.0.0 - SDK for building A2A compliant agents
- **agentvault-testing-utils**: 1.0.0 - Shared testing utilities

### Major Features

#### Library (agentvault)
- Complete A2A protocol implementation
- MCP (Model Context Protocol) support
- Secure local key management
- OAuth2 authentication support
- Environment variable and OS keyring integration
- Comprehensive testing suite

#### CLI (agentvault-cli)
- Agent management commands (list, run, install)
- Configuration management
- Registry interaction
- Key management utilities
- Rich terminal output with progress indicators

#### Registry API (agentvault-registry-api)
- RESTful API for agent discovery
- User authentication and authorization
- Email verification system
- Rate limiting and security features
- PostgreSQL database with async support
- Comprehensive API documentation

#### Server SDK (agentvault-server-sdk)
- FastAPI-based framework for building agents
- Easy route registration
- Built-in authentication middleware
- Docker packaging support
- CLI tool for agent scaffolding

#### Testing Utils (agentvault-testing-utils)
- Shared mocks and fixtures
- HTTP request mocking utilities
- Test helpers for all components

### Security

- All sensitive configuration handled through environment variables
- No hardcoded secrets or credentials
- Proper .gitignore configuration
- JWT-based authentication
- Secure password hashing with bcrypt
- Email verification for user accounts

### Documentation

- Comprehensive README files for all components
- API documentation via OpenAPI/Swagger
- Configuration guides
- Security scanning tools included

### Infrastructure

- Docker support with multi-stage builds
- Poetry-based dependency management
- Monorepo structure with workspace support
- CI/CD ready configuration

### Known Issues

- None reported

### Breaking Changes

- This is the first major release, establishing the baseline API

### Upgrade Notes

As this is the first major release, there are no upgrade notes from previous versions.

## Previous Versions

### [0.2.1] - Library Pre-release
- Initial A2A protocol implementation
- Basic key management features

### [0.1.1] - Components Pre-release
- Initial CLI implementation
- Registry API scaffolding
- Server SDK framework

### [0.1.0] - Initial Development
- Project structure setup
- Basic monorepo configuration
