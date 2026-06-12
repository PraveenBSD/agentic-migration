# AI GitOps Agent For Ingress To Gateway Migration

This document is a presentation-style walkthrough of why Kubernetes teams migrate from NGINX Ingress to Gateway API / Envoy Gateway, and how an AI GitOps agent can automate that migration across many repositories.

---

## 1. Kubernetes Ingress And NGINX Ingress

Kubernetes `Ingress` is an API object used to expose HTTP and HTTPS services outside the cluster.

An Ingress usually defines:

- Host names such as `shop.example.com`
- Paths such as `/api`, `/orders`, or `/`
- Backend Kubernetes Services
- TLS certificates
- Controller-specific behavior through annotations

The Kubernetes Ingress object does not route traffic by itself. It needs an Ingress controller.

NGINX Ingress is one of the most widely used Ingress controllers. It watches Kubernetes Ingress resources and converts them into NGINX configuration.

Teams commonly use NGINX Ingress annotations for advanced behavior:

- URL rewrites
- TLS redirect
- Request size limits
- Timeouts
- Rate limiting
- IP allowlists
- CORS
- Header modification
- Compression
- Canary routing

This annotation-heavy model works, but over time it becomes hard to standardize, validate, and migrate.

---

## 2. Gateway API And Why It Is Replacing Ingress

Gateway API is the next-generation Kubernetes networking API.

It was created to address limitations in the original Ingress API:

- Ingress is small and under-specified for complex traffic management.
- Advanced features depend heavily on controller-specific annotations.
- Different controllers interpret annotations differently.
- Platform teams and application teams often need clearer ownership boundaries.

Gateway API introduces more expressive resources:

- `GatewayClass`: identifies the gateway implementation.
- `Gateway`: represents the entry point into the cluster.
- `HTTPRoute`: defines HTTP routing behavior.
- `ReferenceGrant`: allows safe cross-namespace references.

The key shift is that Gateway API makes traffic behavior part of typed Kubernetes resources instead of opaque annotations.

---

## 3. What Is Envoy Gateway?

Envoy Gateway is an implementation of Kubernetes Gateway API built on Envoy Proxy.

Envoy is a high-performance L7 proxy used widely in cloud native infrastructure. Envoy Gateway provides Kubernetes-native management around Envoy.

Envoy Gateway gives platform teams:

- Gateway API support
- Envoy-powered traffic management
- Clear separation between infrastructure and application routing
- Extensibility through Envoy policies
- A modern path away from annotation-heavy Ingress resources

In this project, Envoy Gateway is the target runtime for migrated NGINX Ingress manifests.

---

## 3.1 Envoy Gateway Policy Model

Gateway API describes the core routing model with resources like `Gateway` and `HTTPRoute`.

Envoy Gateway extends this with policy resources that attach operational behavior to Gateways, Routes, and backend Services.

Important policy concepts:

| Policy | What It Controls | Example Use |
| --- | --- | --- |
| `BackendTrafficPolicy` | Traffic behavior between Envoy and backend services | Rate limiting, retries, timeouts, circuit breaking, load balancing |
| `SecurityPolicy` | Security behavior for traffic entering through Gateway routes | CORS, JWT auth, external auth, authorization rules, IP filtering depending on configuration |
| `BackendTLSPolicy` | TLS settings from the gateway/proxy to backend services | Originate TLS to upstream services, configure backend certificate validation |
| `ClientTrafficPolicy` | Client-facing connection and request behavior at the Gateway edge | Header handling, client connection behavior, protocol options |
| `EnvoyPatchPolicy` | Low-level Envoy xDS patching for features not modeled by higher-level APIs | Advanced Envoy filters such as custom compression or specialized listener/filter behavior |
| Gateway / Route filters | Request and response behavior at route level | URL rewrites, redirects, header modification |

This policy model is important because many NGINX Ingress behaviors are hidden inside annotations. In Envoy Gateway, the goal is to express that behavior as typed Kubernetes resources.

Example:

```text
NGINX Ingress annotation
  nginx.ingress.kubernetes.io/proxy-read-timeout: "90"

Envoy Gateway model
  HTTPRoute for routing
  BackendTrafficPolicy for timeout behavior
```

This makes the migration more than a syntax conversion. It is also a move from annotation-driven configuration to policy-driven configuration.

---

## 4. Feature Usage: NGINX Ingress vs Envoy Gateway

| Capability | NGINX Ingress | Envoy Gateway / Gateway API |
| --- | --- | --- |
| Basic host/path routing | Ingress `rules` | `HTTPRoute` matches |
| Backend service routing | Ingress backend service | `HTTPRoute.backendRefs` |
| TLS termination | Ingress `tls` | `Gateway.listeners.tls` |
| URL rewrite | NGINX annotation | `HTTPRoute` filters where supported |
| Header modification | NGINX snippets/annotations | `HTTPRoute` filters or `ClientTrafficPolicy` for gateway-level header handling |
| Timeouts | NGINX annotations | `BackendTrafficPolicy` |
| Rate limiting | NGINX annotations | `BackendTrafficPolicy` |
| CORS | NGINX annotations/snippets | `SecurityPolicy` |
| IP allowlisting | NGINX annotations | `SecurityPolicy` |
| SSL redirect | NGINX annotation | Listener/route policy depending on implementation |
| Gzip compression | NGINX snippet/config | `EnvoyPatchPolicy` when compression is not exposed through a higher-level policy |

The important migration challenge is that not every NGINX annotation has a one-line Gateway API equivalent. Some behavior maps cleanly to `HTTPRoute`; other behavior needs Envoy Gateway policies or follow-up platform decisions.

---

## 4.1 Feature Migration Examples

The table below shows how common NGINX Ingress features usually translate during migration.

| Feature | NGINX Ingress Example | Envoy Gateway / Gateway API Direction | Migration Notes |
| --- | --- | --- | --- |
| URL rewrites | `nginx.ingress.kubernetes.io/rewrite-target: /$2` | `HTTPRoute` `URLRewrite` filter | Often maps cleanly when the rewrite is path-prefix or host based. Regex-heavy rewrites may need manual review. |
| TLS redirect | `nginx.ingress.kubernetes.io/ssl-redirect: "true"` | `HTTPRoute` `RequestRedirect` filter | Usually represented as an HTTP-to-HTTPS redirect. Exact behavior depends on listener setup. |
| Request size limits | `nginx.ingress.kubernetes.io/proxy-body-size: "20m"` | `BackendTrafficPolicy` with request buffering/body-size settings | In this project, body-size annotations map to `BackendTrafficPolicy` `requestBuffer.limit`. |
| Timeouts | `proxy-read-timeout`, `proxy-send-timeout`, `proxy-connect-timeout` | `BackendTrafficPolicy` timeout settings | In this project, read timeout maps to `BackendTrafficPolicy` `timeout.http.requestTimeout`. Other timeout types may need review. |
| Rate limiting | `limit-rps`, `limit-connections`, `limit-burst-multiplier` | `BackendTrafficPolicy` rate-limit settings | Simple route/backend rate limits belong in `BackendTrafficPolicy`. Global/distributed rate limits may need platform design. |
| IP allowlists | `whitelist-source-range: "10.0.0.0/8"` | `SecurityPolicy` authorization rules | Source IP preservation must be checked with load balancer topology before relying on allowlists. |
| CORS | `enable-cors`, `cors-allow-origin`, `cors-allow-methods` | `SecurityPolicy` CORS settings | Allowed origins, credentials, methods, and headers should be preserved exactly. |
| Header modification | `configuration-snippet`, `proxy_set_header`, `more_set_headers` | `HTTPRoute` `RequestHeaderModifier` / `ResponseHeaderModifier`; `ClientTrafficPolicy` for gateway-level header behavior | Simple add/set/remove headers map well. Arbitrary NGINX snippets need review. |
| Compression | NGINX `server-snippet` with `gzip on` | `EnvoyPatchPolicy` for compression filters when no higher-level policy is available | Compression usually needs Envoy filter-level configuration rather than a basic route match. |
| Canary routing | `canary: "true"`, `canary-weight: "20"` | `HTTPRoute.backendRefs.weight` | Weighted backend routing maps well when the canary is percentage based. Header/cookie canaries need richer route matches. |

The agent should identify these features in the source manifests and call out anything that cannot be converted exactly.

---

## 5. Traffic Flow Comparison

### NGINX Ingress Flow

```text
Client
  |
  v
Load Balancer
  |
  v
NGINX Ingress Controller
  |
  v
Kubernetes Service
  |
  v
Application Pods
```

Traffic behavior is defined by Ingress specs plus NGINX-specific annotations.

### Envoy Gateway Flow

```text
Client
  |
  v
Load Balancer
  |
  v
Envoy Gateway / Envoy Proxy
  |
  v
Gateway + HTTPRoute Rules
  |
  v
Kubernetes Service
  |
  v
Application Pods
```

Traffic behavior is described through Gateway API resources and Envoy Gateway policies.

---

## 6. Problem Statement

Imagine an organization with around 100 clients.

Each client maintains applications in different environments:

- Development
- QA
- Staging
- Production
- Region-specific clusters
- Client-specific GitOps repositories

Across these repositories, there may be hundreds or thousands of NGINX Ingress manifests.

Manual migration is difficult because every repository can be slightly different:

- Different folder structures
- Different naming conventions
- Different NGINX annotations
- Different TLS and host rules
- Different validation requirements
- Different review expectations

The organization needs a repeatable way to:

1. Find Ingress manifests in a repo.
2. Understand what each Ingress does.
3. Convert it to Gateway API / Envoy Gateway resources.
4. Validate the generated YAML.
5. Push the change to a branch.
6. Open a pull request with a useful migration summary.
7. Handle review feedback.

This is a strong fit for AI agents because the work is structured, repetitive, repository-specific, and tool-driven.

### What The Agent Achieves

Without automation, assume one repository migration takes around 2 story points:

```text
100 repositories x 2 story points = 200 story points
```

With the GitOps agent, the first-pass migration work is automated:

- Repository clone
- Manifest discovery
- Ingress-to-Gateway conversion
- YAML validation
- Branch creation
- Pull request creation
- PR summary generation

Engineers can start directly from review instead of beginning from manual conversion.

If review and verification take around 1 story point per repository:

```text
100 repositories x 1 story point = 100 story points
```

So the agent reduces the estimated effort from 200 story points to 100 story points.

The value is not that the agent removes engineers from the process. The value is that engineers spend their time reviewing and validating the generated change instead of repeating the same migration steps across 100 repositories.

---

## 7. What Are Agents?

An AI agent is an LLM-driven system that can reason about a task, choose tools, observe results, and continue until the goal is complete.

Instead of writing one fixed script for every migration path, an agent works in a loop:

```text
Read context
  |
Choose a tool
  |
Run the tool
  |
Observe result
  |
Choose next step
  |
Repeat until done
```

In this project, the LLM does not directly edit random files or run arbitrary shell commands. It uses a curated set of tools.

That gives the system flexibility while keeping the blast radius controlled.

---

## 8. GitOps Agent: Core Idea

The GitOps agent is designed to behave like a careful automation engineer working through a repository.

It receives:

- Repository URL
- Manifest path
- Optional branch name
- Migration skill
- Available tools

It then performs the migration through tool calls.

### Core Components

| Component | Purpose |
| --- | --- |
| `apps/agent-api` | FastAPI backend and agent runtime |
| `apps/agent-ui` | Streamlit chatbot and direct migration UI |
| `apps/agent-api/skills` | Skill files that describe task-specific workflows |
| `apps/agent-api/tools` | Tool implementations for GitHub, conversion, validation, editing |
| `examples/retail-platform` | Example Kubernetes app used for local demos |
| `agentic-app` | Helm chart for deploying the API and UI |

### Tools Used By The Agent

| Tool | Purpose |
| --- | --- |
| `load_skill` | Loads the right skill file for the user request |
| `clone_repo` | Clones or copies the target repo and creates a migration branch |
| `convert_ingress` | Converts NGINX Ingress manifests to Gateway API resources |
| `validate_yaml` | Validates generated Kubernetes YAML |
| `push_branch` | Commits and pushes the migration branch |
| `create_github_pr` | Opens or updates a GitHub pull request |
| `modify_yaml_file` | Applies review-driven YAML corrections |

### How It Is Built

The backend agent loop is intentionally small:

1. Build context from the API request.
2. Load the relevant migration skill.
3. Let the LLM choose the next tool.
4. Execute the tool.
5. Store the tool result in state.
6. Tell the LLM the next step from the skill plan.
7. Continue until the PR step or end step is reached.

The agent is generic. The migration behavior comes from the skill file:

```text
apps/agent-api/skills/migrate-nginx-to-envoy-skill.md
```

That means more GitOps skills can be added later without rewriting the whole agent loop.

---

## 9. Small Example Walkthrough

Example request:

```text
Migrate https://github.com/example/retail-platform.git
from NGINX Ingress to Envoy Gateway.
Manifest path: k8s/overlays/prod/ingress
Branch: agentic-gateway-migration-retail
```

Typical agent flow:

1. User asks for an Ingress to Gateway migration.
2. Agent calls `load_skill`.
3. Skill tells the agent how to perform this migration.
4. Agent calls `clone_repo`.
5. Repository is cloned and a migration branch is created.
6. Agent calls `convert_ingress`.
7. Ingress YAML is converted into Gateway API / Envoy Gateway resources.
8. Agent calls `validate_yaml`.
9. Generated YAML is checked.
10. Agent calls `push_branch`.
11. Migration changes are committed and pushed.
12. Agent calls `create_github_pr`.
13. Pull request is created with a reviewer-friendly summary.

The PR description should explain:

- Which Ingress files were found
- What behavior those Ingress resources had
- What Envoy Gateway / Gateway API resources were generated
- What validation was performed
- Any behavior that could not be converted exactly

---

## Demo With Bundled Example

This repository includes a local example:

```text
Repository URL: example://retail-platform
Manifest path: k8s/overlays/prod
```

Run the API:

```bash
cd apps/agent-api
pip install -r requirements.txt
uvicorn main:app --reload
```

Run the UI:

```bash
cd apps/agent-ui
pip install -r requirements.txt
streamlit run app.py
```

The Streamlit UI lets you:

- Ask what skills the agent has
- Start a migration conversation
- Provide repository details
- Review the plan
- Approve execution
- View migration status, logs, and PR output

---

## LLM Provider

The backend supports OpenAI, Gemini, and Ollama through LangChain-compatible chat models.

For local Ollama:

```bash
ollama serve
ollama pull llama3.1
export MIGRATION_LLM_PROVIDER=ollama
export MIGRATION_LLM_MODEL=llama3.1
export OLLAMA_BASE_URL=http://localhost:11434
```

For GitHub push and PR creation:

```bash
export GITHUB_TOKEN="your-github-token"
```

---

## More Detail

For the implementation walkthrough, see:

```text
AGENTIC_MIGRATION.md
```
