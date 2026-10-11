# Project Instructions

## Python Environment

This application uses the user's shared virtual environment at `~/.efenv`,
which serves as their machine-wide Python environment. The absence of a
repository-local `env`, `venv`, or `.venv` directory is intentional.

- Use `~/.efenv/bin/python` for Python scripts, tests, and dependency checks.
  Calling it directly does not require activating the environment.
- Use `~/.efenv/bin/python -m pip` when dependency management is needed.
- Do not create a repository-local virtual environment for routine work.
- Before reporting a missing dependency, check it with `~/.efenv/bin/python`.
- Run the test suite from the repository root with
  `~/.efenv/bin/python -m unittest discover -s tests`.
- Use `make up` to start the application; the `makefile` activates `~/.efenv`.
