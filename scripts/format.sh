#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "${SCRIPT_DIR}/.."

echo "Formatting project..."
ruff check . --select I --fix --silent
ruff format .

echo "Project formatted!"
