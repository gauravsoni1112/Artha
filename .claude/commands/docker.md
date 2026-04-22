---
allowed-tools: Bash(docker compose:*), Read(./infra/**)
argument-hint: up [services...] | down | ps | logs [service]
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
- `/docker up api cashflow_agent investment_agent tax_agent risk_agent goal_agent`
- `/docker ps`
- `/docker logs risk_agent`
- `/docker down`
