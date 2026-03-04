#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "${SCRIPT_DIR}/.."

echo "Cleaning the project..."
rm -rf ./venv
rm -rf ./.venv
rm -rf ./.ruff_cache
rm -rf ./data
rm -rf ./container-data
rm ./.env
rm ./*.db

echo "Project cleaned!"
