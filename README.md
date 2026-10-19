# spotter-backend

Django API that plans the cheapest fuel stops for a road trip between two US locations.

## Environments

| Env     | Settings module            | Image target | Host port | Database container   | Migrations            |
|---------|----------------------------|--------------|-----------|----------------------|-----------------------|
| local   | `config.settings.local`    | `local`      | 8000      | `spotter-local-db`   | auto on start         |
| dev     | `config.settings.dev`      | `production` | 8001      | `spotter-dev-db`     | auto on start         |
| staging | `config.settings.staging`  | `production` | 8002      | `spotter-staging-db` | auto on start         |
| prod    | `config.settings.prod`     | `production` | 8003      | `spotter-prod-db`    | explicit release step |

Containers are `spotter-<env>-web` and `spotter-<env>-db`. dev, staging and prod run the same image;
only environment variables and the settings module differ. Select one with `make up ENV=<env>`.
Database and role names use underscores (`spotter_prod_db`, `spotter_prod`) so they never need quoting.
