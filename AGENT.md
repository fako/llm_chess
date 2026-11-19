## Workspace

You are working in a shielded workspace where your user has its own home on a Debian box with Python 3.12 as its main program. You are completely whitelisted for this environment and can do anything you want, except for leaving this sandbox and the home folder. Prefer the usage of Python when writing code or scripts, but the alternative is to ask your human to install more software for you.

## Project stack

The prefered stack for projects is:
* Python+Django+Ninja
* Postgres
* Redis
* Tika
* Invoke (CLI library in Python)
* Jinja2+HTMX+Tailwind

You are not required to use the full stack, but when picking a tool make sure the choice aligns with the prefered choices or consult your human.

## Python environment

This workspace uses `venv` as the project virtual environment. Keep Python dependencies in `pyproject.toml`, then ask your human to `invoke runtimes.install --workspace-module={{ workspace.module }} --name=<runtime>` from the control repository or run the equivalent inside this workspace:

```bash
python3 -m venv venv --copies --upgrade-deps
venv/bin/python -m pip install -e .
```

The supervisor-managed web process runs through `venv/bin/python`, so install dependencies there before expecting the service to start.
Static files are gathered through collectstatic and end up in staticfiles/

## workspace.json

`workspace.json` in the root of this repository is how you tell an installation how to run this project. It travels with the repository: the hub you work on and the production server read the same file. Keep it up to date whenever you add a runtime or a step that installing or deploying needs. Describe the project only: never a domain, a port, a secret value or a commit hash, because those belong to the installation.

| Key | Meaning |
|---|---|
| `name`, `module` | The project's human name and the module it proposes to run under |
| `repository` | The SSH URL of the git remote, for example `git@github.com:owner/project.git` |
| `branch` | The branch installations follow, or `null` for the remote's default |
| `runtimes` | One entry per process: `type` (`django`, `celery`), `module` (the Python package), `primary` (answers to the project's own name), `expose` (a label that makes another runtime reachable as `<label>-{{ workspace.slug }}.<zone>`) and `configuration` for the rest, such as `{"workers": 4}` or `{"queues": ["default"]}` |
| `environment` | Names of the environment variables the project needs set, without values |
| `command_sets` | Named lists of shell commands, run in the home directory with the virtualenv and `.env` loaded. They may ask for input |
| `pre_install`, `post_install` | Command set name(s) run before runtimes first start, and after |
| `pre_deploy`, `post_deploy` | Command set name(s) run on every update: before runtimes restart on the new code (while the old code still serves), and after |

A hook takes one command set name or a list of names. For example, asset building usually belong in `pre_deploy`, and creating a first superuser in `post_install`. Command sets cannot install system packages: ask your human when you need one. Migrations are not part of deploy command sets, because removing columns needs a different timing than adding columns. Add a "migration" command set to allow running migrations and give the human instructions on what the timing should be.

Adding, removing or renaming a runtime or an exposure changes how the project is set up, and needs your human to run `invoke workspaces.configure` on every installation. Changes to command sets and hooks go out with a normal deploy.

## How domains resolve

This runtime answers to more than one name, and which one to use depends on where the caller is.

* **A browser** reaches the workspace's primary runtime at `<scheme>://{{ workspace.slug }}.<zone>/`, through the installation's edge. The zone is `localhost` on a laptop and a real domain on a hub or a vps. Another runtime is only reachable from a browser once it is exposed, as `<label>-{{ workspace.slug }}.<zone>`.
* **Another container** n8n, or another workspace's runtime uses `http://runtimes.workspaces:7000/r/{{ workspace.slug }}/<runtime>/`. The workspace and runtime travel in the path, not the hostname, so only that one name has to resolve. It is the same address on every installation, so use it in anything that might move, such as workflows.
* **Never call `{{ workspace.slug }}.localhost` from inside a container.** It does resolve, to the *calling* container's own loopback, so the mistake surfaces as a refused connection rather than an unknown host. This is the confusing one.
* **Names are management's.** Do not hand-write nginx server blocks: they are generated and will be overwritten on the next `invoke runtimes.apply`.
