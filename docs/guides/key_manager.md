# Developer Guide: KeyManager (`agentvault.key_manager`)

The `KeyManager` is a core component of the `agentvault` library responsible for securely managing the credentials (API Keys, OAuth 2.0 Client ID/Secret) that client applications need to authenticate with remote A2A agents.

## Purpose

*   **Abstraction:** Provides a unified interface (`get_key()`, `get_oauth_client_id()`, etc.) to retrieve credentials, hiding the underlying storage mechanism (Environment Variables, Files, OS Keyring).
*   **Security:** Facilitates secure storage by prioritizing the OS Keyring when available and configured.
*   **Flexibility:** Allows loading credentials from standard sources commonly used in development and deployment workflows.

## Credential Sources & Priority

`KeyManager` loads credentials upon initialization and retrieves them on demand, checking sources in the following order:

1.  **Key File Cache (.env or .json):** If a `key_file_path` was provided during initialization, credentials found in that file are loaded into an internal cache. This source takes the highest priority.
2.  **Environment Variable Cache:** If `use_env_vars=True` (default), credentials found in environment variables matching the expected patterns are loaded into the cache *only if not already loaded from the file*.
3.  **OS Keyring (On Demand):** If `use_keyring=True` and a requested credential (`get_key`, `get_oauth_client_id`, etc.) was *not* found in the file or environment caches, `KeyManager` will attempt to load it directly from the OS Keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service via `keyring` library).

**Important:** The keyring is checked *on demand* during `get_` calls if the credential isn't already cached from file/env. Credentials loaded from the keyring are then cached internally for the lifetime of the `KeyManager` instance.

## Service Identifier

The `service_id` parameter used in `KeyManager` methods (e.g., `km.get_key("openai")`) is the **key** to retrieving the correct credential.

*   **Definition:** A user-defined string acting as a local alias for a specific set of credentials.
*   **Case-Insensitive:** `KeyManager` normalizes `service_id` to lowercase internally for lookups.
*   **Source:**
    *   Often corresponds to the `service_identifier` field within an `AgentCard`'s `authSchemes`. The `AgentVaultClient` uses this automatically.
    *   Can be explicitly provided by the user/application (e.g., via `agentvault_cli run --key-service <your_id>`).
*   **Purpose:** Allows mapping multiple agents requiring the same credentials (e.g., several agents using the same OpenAI API key) to a single locally stored secret identified by a common `service_id` like `"openai"`.

## Storage Conventions

The `KeyManager` expects credentials to be stored using specific conventions depending on the source:

| Credential Type     | Source        | Convention                                                            | Example                                       |
| :------------------ | :------------ | :-------------------------------------------------------------------- | :-------------------------------------------- |
| **API Key**         | Env Var       | `AGENTVAULT_KEY_<SERVICE_ID_UPPER>`                                   | `AGENTVAULT_KEY_OPENAI`                       |
|                     | File (.env)   | `<service_id_lower>=key_value`                                       | `openai=sk-...`                               |
|                     | File (.json)  | `{ "<service_id>": "key_value" }` or `{ "<service_id>": {"apiKey": ...}}` | `{ "openai": "sk-..." }`                      |
|                     | Keyring       | Service: `agentvault:<service_id>`, Username: `<service_id>`            | Service: `agentvault:openai`, User: `openai` |
| **OAuth Client ID** | Env Var       | `AGENTVAULT_OAUTH_<SERVICE_ID_UPPER>_CLIENT_ID`                      | `AGENTVAULT_OAUTH_GOOGLE_CLIENT_ID`           |
|                     | File (.env)   | `AGENTVAULT_OAUTH_<service_id_lower>_CLIENT_ID=id_value`             | `AGENTVAULT_OAUTH_google_CLIENT_ID=...`       |
|                     | File (.json)  | `{ "<service_id>": {"oauth": {"clientId": "id_value", ...}}}`         | `{ "google": {"oauth": {"clientId": ...}}}`   |
|                     | Keyring       | Service: `agentvault:oauth:<service_id>`, Username: `clientId`          | Service: `agentvault:oauth:google`, User: `clientId` |
| **OAuth Secret**    | Env Var       | `AGENTVAULT_OAUTH_<SERVICE_ID_UPPER>_CLIENT_SECRET`                   | `AGENTVAULT_OAUTH_GOOGLE_CLIENT_SECRET`       |
|                     | File (.env)   | `AGENTVAULT_OAUTH_<service_id_lower>_CLIENT_SECRET=secret_value`      | `AGENTVAULT_OAUTH_google_CLIENT_SECRET=...`   |
|                     | File (.json)  | `{ "<service_id>": {"oauth": {..., "clientSecret": "secret_value"}}}` | `{ "google": {"oauth": {"clientSecret": ...}}}`|
|                     | Keyring       | Service: `agentvault:oauth:<service_id>`, Username: `clientSecret`      | Service: `agentvault:oauth:google`, User: `clientSecret`|

*(Note: `<SERVICE_ID_UPPER>` means the `service_id` converted to uppercase, `<service_id_lower>` means lowercase)*

## Initialization

```python
from agentvault import KeyManager
import pathlib

# Option 1: Defaults - Load from Env Vars only, Keyring disabled
km_default = KeyManager()

# Option 2: Load from Env Vars AND use Keyring if needed
# (Requires 'keyring' package and backend to be installed/functional)
km_env_keyring = KeyManager(use_keyring=True)

# Option 3: Load ONLY from a specific .env file
# (Disables Env Vars and Keyring)
km_file_only = KeyManager(
    key_file_path=pathlib.Path("./secrets.env"),
    use_env_vars=False,
    use_keyring=False
)

# Option 4: Load from File THEN Env Vars (File overrides Env)
km_file_then_env = KeyManager(
    key_file_path="./my_keys.json",
    use_env_vars=True, # Default
    use_keyring=False
)

# Option 5: Load from File, then Env, then Keyring
km_all = KeyManager(
    key_file_path="./conf/agent_keys.env",
    use_env_vars=True,
    use_keyring=True
)

# Option 6: Use custom Env Var prefixes
km_custom_prefix = KeyManager(
    env_prefix="MYAPP_APIKEY_",
    oauth_env_prefix="MYAPP_OAUTHCFG_"
)
```

## Usage

### Retrieving Credentials

```python
# Assuming km = KeyManager(use_keyring=True)

# Get API Key
openai_key = km.get_key("openai") # Case-insensitive lookup
if openai_key:
    print(f"OpenAI Key found: {openai_key[:4]}...")
    source = km.get_key_source("openai")
    print(f"Source: {source}") # e.g., 'env', 'file', 'keyring'
else:
    print("OpenAI Key not found.")

# Get OAuth Credentials for an agent identified as 'my-google-agent'
google_agent_client_id = km.get_oauth_client_id("my-google-agent")
google_agent_client_secret = km.get_oauth_client_secret("my-google-agent")

if google_agent_client_id and google_agent_client_secret:
    print(f"Found OAuth credentials for my-google-agent:")
    print(f"  Client ID: {google_agent_client_id}")
    # Avoid printing the secret!
    status_str = km.get_oauth_config_status("my-google-agent")
    print(f"  Status: {status_str}")
elif google_agent_client_id or google_agent_client_secret:
    print("Partially found OAuth credentials for my-google-agent (missing ID or Secret).")
else:
    print("OAuth credentials for my-google-agent not found.")
```

### Storing Credentials (via OS Keyring)

These methods are primarily intended for use by setup tools like `agentvault_cli config set`.

```python
from agentvault import KeyManagementError

# Needs use_keyring=True during init
km = KeyManager(use_keyring=True)

try:
    # Store an API Key
    km.set_key_in_keyring("anthropic", "sk-ant-...")
    print("Anthropic key stored.")

    # Store OAuth Credentials
    km.set_oauth_creds_in_keyring(
        "some_oauth_service",
        "your-client-id-here",
        "your-client-secret-here"
    )
    print("OAuth credentials stored.")

except KeyManagementError as e:
    print(f"Error storing credential in keyring: {e}")
    # Handle error (e.g., keyring backend not available)
except ValueError as e:
    print(f"Input error: {e}")

```

## Security Considerations

*   **OS Keyring is Preferred:** Storing credentials directly in environment variables or plain text files (`.env`, `.json`) carries risks if the environment or file system is compromised. The OS Keyring provides platform-native secure storage.
*   **File Permissions:** If using file-based storage, ensure the key file has strict permissions (e.g., `chmod 600` on Linux/macOS) so only the owner can read it.
*   **Environment Variables:** Be cautious about where and how environment variables are set, especially in shared or logged environments. Avoid committing them to version control.
*   **Error Handling:** The `get_` methods return `None` if a credential isn't found. Methods that interact with the keyring (`set_...`, or `get_...` when loading from keyring) can raise `KeyManagementError` if the keyring backend is unavailable or fails.
