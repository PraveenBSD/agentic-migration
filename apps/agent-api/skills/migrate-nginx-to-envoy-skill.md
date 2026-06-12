# Migrate NGINX Ingress To Envoy Gateway

Use this skill when the user asks to migrate Kubernetes NGINX Ingress manifests to Envoy Gateway, Gateway API, or HTTPRoute resources.

## Goal

Convert the requested Ingress manifests in the target Git repository, validate the generated YAML, push the migration branch, and open or update a GitHub pull request for human review. Never close or merge pull requests.

## Workflow

1. Clone the repository with `clone_repo`.
2. Use the migration branch from context. If no branch is provided, use `suggested_branch_name`. Do not use `main`, `master`, or `develop` as the migration branch.
3. Convert the requested manifest path with `convert_ingress`.
4. Validate the converted YAML with `validate_yaml` using the real validation path saved by conversion.
5. Write the actual Markdown PR description text for this migration process from the source manifests, conversion output, generated resources, and validation logs.
6. Push the branch with `push_branch`.
7. Create the PR with `create_github_pr`. In the `description` argument, pass the full Markdown PR description text written in step 5. Do not pass a placeholder, a step reference, or text such as `Migration summary from step 5`.
8. Stop the agent run after the pull request step returns a PR URL, updates an existing open PR, or clearly says a PR cannot be created. Do not call more tools after this stop condition. Do not close or merge the PR.

## PR Description

Write a concise Markdown PR description that includes:

- Summary of the migration.
- Ingress files found.
- Important Ingress behavior: hosts, paths, backends, TLS, rewrites, timeouts, body-size limits, canary behavior, and header behavior when present.
- Equivalent Envoy Gateway / Gateway API changes.
- Validation result.

The `description` value passed to `create_github_pr` must be the complete Markdown body itself. Never use placeholder text such as `Migration summary from step 5`, `see above`, `TBD`, or a reference to another step.

Do not claim behavior that is not visible in the source manifests, generated output, or validation logs.

## Recovery Notes

- If validation fails because schemas are unavailable but YAML syntax is valid, continue and mention that in the PR.
- If conversion cannot represent a feature exactly, call it out in the PR description.
- If a tool fails, adjust the next tool call instead of repeating the same failing input.
