---
allowed-tools: Bash(docker compose:*), Read(./infra/**)
argument-hint: up [services...] | down | build | rebuild | ps | logs [service]
description: Manage the Artha Docker Compose stack
---

Work only with the Artha Docker Compose file at @infra/docker-compose.yml.

Interpret the first argument as the action:

- `up`
  Run:
  `docker compose -f infra/docker-compose.yml up -d --build`
  If service names are also provided, append them after `--build`.

- `down`
  Run:
  `docker compose -f infra/docker-compose.yml down`

- `build`
  Build images without starting containers.
  Run:
  `docker compose -f infra/docker-compose.yml build`
  If service names are provided, append them.

- `rebuild`
  Full clean rebuild sequence — stops containers, rebuilds all images from scratch (no cache), then starts containers.
  Run in order:
  1. `docker compose -f infra/docker-compose.yml down`
  2. `docker compose -f infra/docker-compose.yml build --no-cache`
  3. `docker compose -f infra/docker-compose.yml up -d`
  If service names are provided, pass them to steps 2 and 3.

- `ps`
  Run:
  `docker compose -f infra/docker-compose.yml ps`

- `logs`
  Expect the next argument to be the service name.
  Run:
  `docker compose -f infra/docker-compose.yml logs --tail=200 <service>`
  Summarize the most relevant warnings, errors, or readiness signals instead of dumping raw output.

Behavior rules:

- Execute the requested Docker command instead of only describing it.
- Keep responses concise and action-oriented.
- If the action is missing or invalid, explain the supported forms and give short examples.
- If `logs` is requested without a service name, ask for the service name.

Examples:

- `/docker up`
- `/docker up api cashflow_agent`
- `/docker build`
- `/docker build api frontend`
- `/docker rebuild`
- `/docker rebuild api`
- `/docker down`
- `/docker ps`
- `/docker logs risk_agent`
