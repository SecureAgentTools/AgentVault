# Docker Deployment Guide for AgentVault Registry

## 🚨 SECURITY WARNING 🚨

**NEVER commit sensitive credentials to version control!** Always use environment variables or secure secret management systems.

## Setup Instructions

1. **Create your environment configuration**:
   ```bash
   cp .docker.env.example .docker.env
   ```

2. **Edit `.docker.env` with your secure values**:
   ```bash
   # Generate a secure API key secret (64 characters)
   openssl rand -hex 32
   ```
   
   Update the `.docker.env` file with:
   - A strong database password
   - The generated API key secret
   - Any other custom configuration

3. **Create your docker-compose.yml**:
   ```bash
   cp docker-compose.yml.example docker-compose.yml
   ```

4. **Add to .gitignore** (CRITICAL!):
   ```bash
   echo -e "\n# Docker secrets\n.docker.env\ndocker-compose.yml" >> ../.gitignore
   ```

5. **Start the services**:
   ```bash
   docker-compose --env-file .docker.env up -d
   ```

## Security Best Practices

1. **NEVER commit these files to version control**:
   - `.docker.env`
   - `docker-compose.yml` (if it contains any secrets)
   - Any `.env` files with real credentials

2. **Always use environment variables** for sensitive data
3. **Generate strong secrets** using cryptographically secure methods
4. **Rotate secrets regularly** in production environments

## Verifying Security

Before committing, always check:
```bash
git status
```

Ensure no sensitive files are staged for commit!

## Production Deployment

For production deployments:

1. Use a proper secret management system (e.g., HashiCorp Vault, AWS Secrets Manager)
2. Consider using Docker Swarm secrets or Kubernetes secrets
3. Enable TLS/SSL for all services
4. Use strong, unique passwords for all services
5. Implement proper access controls and authentication

## Troubleshooting

If you accidentally committed secrets:
1. Immediately rotate all exposed credentials
2. Use `git filter-branch` or BFG Repo-Cleaner to remove sensitive data from history
3. Force push the cleaned history (coordinate with team members)
4. Consider the credentials compromised and replace them everywhere they were used
