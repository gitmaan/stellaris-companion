.PHONY: dev build build-python build-electron clean install

# Development
dev:
	./dev.sh

# Install dependencies
install:
	pip install .
	cd electron && npm install
	cd electron/renderer && npm install

# Build everything
build: build-python build-electron

build-python:
	./scripts/build-python.sh

build-electron:
	./scripts/build-electron.sh

# Clean build artifacts
clean:
	rm -rf dist-python/
	rm -rf electron/dist/
	rm -rf electron/renderer/dist/

# Run just the Python backend
backend:
	@if [ -f .env ]; then export $$(grep -v '^#' .env | xargs); fi && \
	STELLARIS_API_TOKEN=dev-token-123 \
	STELLARIS_DB_PATH=./stellaris_history.db \
	python -m backend.electron_main

# Run just Electron (assumes backend running)
electron:
	cd electron && npm run dev
