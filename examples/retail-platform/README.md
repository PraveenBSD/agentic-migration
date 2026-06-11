# Retail Platform Migration Example

This bundled template is a small GitOps-style Kubernetes application used to exercise the migration agent without a remote GitHub repository.

Use these values in the Streamlit UI:

- Repository URL: `example://retail-platform`
- Manifest path: `k8s/overlays/prod`

The Ingress manifest intentionally includes Nginx annotations for request timeout, body size, rewrite behavior, and underscore headers so the converter and agent have policy edge cases to process.
