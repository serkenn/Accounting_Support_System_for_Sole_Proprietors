.PHONY: help setup check test lint fmt safe

help:
	@echo "setup  依存の同期と git フックの登録"
	@echo "check  lint + test + safe （コミット前にこれを通す）"
	@echo "safe   公開リポジトリに出せない情報が混ざっていないかの検査"

setup:
	uv sync --extra dev
	git config core.hooksPath .githooks
	@echo "git フックを .githooks に向けました"

check: lint test safe

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

safe:
	uv run shiwake check-public-safe --root .
