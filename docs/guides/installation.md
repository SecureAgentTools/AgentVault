# Installation Guide

This guide covers how to install the different parts of the AgentVault ecosystem, depending on your needs.

## 1. Installing for Usage (CLI & Client Library)

If you want to **use** the AgentVault CLI to interact with agents or use the `agentvault` client library in your own Python projects, install the desired components directly from PyPI (Python Package Index).

**Prerequisites:**

*   Python 3.10 or 3.11 installed.
*   `pip` (Python's package installer, usually included with Python).
*   **(Optional but Recommended) OS Keyring Backend:** For secure credential storage with the CLI/Library (`keyring` library extras might be needed depending on your OS - see [Keyring documentation](https://keyring.readthedocs.io/)).

**Installation Options:**

*   **CLI Tool (`agentvault-cli`):**
    *   Includes the core `agentvault` library as a dependency.
    ```bash
    # Basic installation
    pip install agentvault-cli

    # Recommended: Install with OS Keyring support for secure credential storage
    pip install "agentvault-cli[os_keyring]"
    ```

*   **Client Library Only (`agentvault`):**
    *   Use this if you only need to interact with agents programmatically from your own Python code and don't need the CLI application.
    ```bash
    # Basic installation
    pip install agentvault

    # Recommended: Install with OS Keyring support
    pip install "agentvault[os_keyring]"
    ```

*   **Server SDK Only (`agentvault-server-sdk`):**
    *   Use this if you are *building* your own A2A-compliant agent server.
    *   Installs the `agentvault` client library as a dependency.
    ```bash
    pip install agentvault-server-sdk
    ```

**Verification (CLI):**

After installing the CLI, check that the command is available:

```bash
agentvault_cli --version
# Expected output: agentvault-cli, version X.Y.Z
```

**Using the Public Registry:**

The CLI and library can interact with the publicly hosted AgentVault Registry.

*   **Registry URL:** `https://agentvault-registry-api.onrender.com`
*   **Configure:**
    *   **Environment Variable (Recommended):**
        *   Linux/macOS: `export AGENTVAULT_REGISTRY_URL=https://agentvault-registry-api.onrender.com`
        *   Windows PowerShell: `$env:AGENTVAULT_REGISTRY_URL='https://agentvault-registry-api.onrender.com'`
        *   Windows Cmd: `set AGENTVAULT_REGISTRY_URL=https://agentvault-registry-api.onrender.com`
    *   **CLI Flag:** Use `--registry https://agentvault-registry-api.onrender.com` with commands like `discover` or `run` (if using an agent ID).
*   **Note (Cold Start):** The public registry runs on Render's free tier. It may take **up to 60 seconds** to respond to the first request after inactivity. Visit `/health` or `/ui` to wake it up.
*   **Developer Account:** Register at [`https://agentvault-registry-api.onrender.com/ui/register`](https://agentvault-registry-api.onrender.com/ui/register).

## 2. Setting up for Development (Contributing or Running from Source)

If you want to contribute to AgentVault, run components locally from the source code (like the registry API), or use features not yet released on PyPI, follow these steps to set up the monorepo development environment.

**Prerequisites:**

*   Git
*   Python 3.10 or 3.11
*   [Poetry](https://python-poetry.org/docs/#installation) (version 1.2+ recommended)
*   **(Optional) PostgreSQL Server:** Required *only* if running the `agentvault_registry` locally.
*   **(Optional) SMTP Server/Service:** Required *only* for local registry email features (verification, password reset).

**Steps:**

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/SecureAgentTools/AgentVault.git
    cd AgentVault
    ```

2.  **Install Dependencies (using Poetry):** Navigate to the project root (`AgentVault/`) and install dependencies for the entire workspace:
    ```bash
    # Installs ALL production AND development dependencies for ALL packages
    poetry install --with dev

    # To include optional OS Keyring support across components:
    # poetry install --with dev --extras os_keyring
    ```
    *   This reads all `pyproject.toml` files.
    *   It creates a single shared virtual environment (usually `.venv/` in the root).
    *   It installs all packages (library, cli, sdk, registry, testing-utils) in *editable* mode, along with their dependencies and development tools (like `pytest`, `httpx`, `uvicorn`, `alembic`, `mkdocs`).

3.  **Activate Virtual Environment:** Before running any code, tests, or tools from source, activate the Poetry-managed environment:
    *   **Recommended:** Use `poetry shell` from the project root. This spawns a new shell with the environment activated.
    *   **Manual Activation (Example):**
        *   Linux/macOS: `source .venv/bin/activate`
        *   Windows PowerShell: `.\.venv\Scripts\Activate.ps1`
        *   Windows Cmd: `.\.venv\Scripts\activate.bat`
    Your prompt should now indicate you are inside the `(.venv)` environment.

4.  **Verify Setup:** Check access to installed tools:
    ```bash
    agentvault_cli --version
    pytest --version
    mkdocs --version
    uvicorn --version
    ```

You can now run components directly from source (e.g., `uvicorn agentvault_registry.main:app` from the `agentvault_registry` directory) or run tests (`pytest agentvault_library/tests/`).

## 3. Running the Registry Locally (Development)

To run the `agentvault_registry` API service locally:

1.  **Complete Development Setup:** Follow the steps in section 2 above. Ensure **PostgreSQL** is running.
2.  **Navigate:** `cd agentvault_registry`
3.  **Configure `.env`:**
    *   Copy `.env.example` to `.env`.
    *   Edit `.env` and set `DATABASE_URL` to your PostgreSQL connection string (using `asyncpg` driver, e.g., `postgresql+asyncpg://user:pass@host:port/dbname`).
    *   Set `API_KEY_SECRET` (e.g., `openssl rand -hex 32`).
    *   **(Optional)** Configure `MAIL_...` variables for email features.
4.  **Database Migrations:** Activate the virtual environment (`poetry shell` or `source .venv/bin/activate`) and run from the `agentvault_registry/` directory:
    ```bash
    alembic upgrade head
    ```
5.  **Run Server:** From the `agentvault_registry/` directory (with venv active):
    ```bash
    uvicorn agentvault_registry.main:app --reload --host 0.0.0.0 --port 8000
    ```

The local registry API will be available at `http://localhost:8000`. Docs at `/docs`, UI at `/ui`.
