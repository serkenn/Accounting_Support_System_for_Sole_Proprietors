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

# LICENSE は名前検査の唯一の例外。著作権者名は公開されることが前提であり、
# ここを伏せると MIT の要件（著作権表示の保持）を満たせなくなるため。
# 例外を増やすときは、必ず理由をここに書くこと。
#
# ★名前ベースの検査（第1層）は、一覧を公開側に置けないので CI では動かない。
#   隣に非公開リポジトリがあれば、その一覧を注入して実行する。
#   これが無いと「仕様書の例からそのまま写した取引先名」のような漏洩を
#   公開側だけでは検出できない。
DENYLIST ?= ../ledger-data/config/denylist.txt

safe:
	@if [ -f "$(DENYLIST)" ]; then \
		echo "名前ベースの検査: 有効（$(DENYLIST)）"; \
		uv run shiwake check-public-safe --root . --exclude LICENSE --denylist "$(DENYLIST)"; \
	else \
		echo "WARNING: $(DENYLIST) が見つかりません。名前ベースの検査は動きません。"; \
		uv run shiwake check-public-safe --root . --exclude LICENSE; \
	fi
