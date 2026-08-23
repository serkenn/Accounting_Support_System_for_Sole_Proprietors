"""投入 API の HTTP 層（第9部 §4.2）。

  POST /api/inbox      写真か PDF を1件積む
  GET  /api/inbox/stats 積んである件数と最古の日付（§4.4）
  GET  /healthz         コンテナの生存確認（認証不要・情報を返さない）

★これ以外の口を増やさない。読みは静的配信が担当する（§10）。
"""

# ★このファイルだけ `from __future__ import annotations` を使わない。
#   注釈が文字列になると、FastAPI が Depends(require_access) を解決できない
#   （require_access はこの関数の中のローカル名で、モジュールの globals に無い）。
#   解決に失敗しても例外にはならず、**依存が消えて素通りする**。
#   認証が黙って外れる形になるので、ここは実物の注釈のまま書く。

import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from .access import ACCESS_HEADER, AccessError, JwksCache, verify_access_token
from .api import IngestSettings, StoreError, inbox_stats, store_upload

#: 1分あたりの受け付け上限（第9部 §4.3）。
RATE_LIMIT_PER_MINUTE = 60


def create_app(settings: IngestSettings | None = None) -> FastAPI:
    # ★設定が揃わなければここで例外になり、起動しない。
    #   認証なしで上がってしまう状態を作らない（S13）。
    settings = settings or IngestSettings.from_env()
    jwks = JwksCache(settings.jwks_url)
    issuer = f"https://{settings.access_team_domain}"
    seen: dict[str, list[float]] = {}

    app = FastAPI(title="shiwake ingest", docs_url=None, redoc_url=None, openapi_url=None)

    def require_access(
        request: Request,
        assertion: Annotated[str, Header(alias=ACCESS_HEADER)] = "",
    ) -> dict:
        try:
            claims = verify_access_token(
                assertion, jwks.get(), aud=settings.access_aud, issuer=issuer
            )
        except AccessError as e:
            # ★理由を詳しく返さない。総当たりの手掛かりになる。
            raise HTTPException(status_code=401, detail="認証できません") from e

        # 誰あたりで数える。Access を通っているので email は信用してよい。
        import time

        who = str(claims.get("email") or claims.get("sub") or "?")
        now = time.monotonic()
        recent = [t for t in seen.get(who, []) if now - t < 60]
        if len(recent) >= RATE_LIMIT_PER_MINUTE:
            raise HTTPException(status_code=429, detail="送信が多すぎます")
        recent.append(now)
        seen[who] = recent
        return claims

    @app.get("/healthz")
    def healthz() -> dict:
        # ★何も明かさない。件数もパスもバージョンも返さない。
        return {"ok": True}

    @app.post("/api/inbox", status_code=201)
    async def post_inbox(
        file: Annotated[UploadFile, File()],
        _claims: Annotated[dict, Depends(require_access)],
        hint: Annotated[str | None, Form()] = None,
    ) -> JSONResponse:
        # ★ file.filename は読まない。使う口を作らない（S11）。
        data = await file.read(settings.max_bytes + 1)

        parsed = None
        if hint:
            try:
                parsed = json.loads(hint)
            except json.JSONDecodeError:
                # 自由記述として受ける。捨てない。
                parsed = {"note": hint}
            if not isinstance(parsed, dict):
                parsed = {"note": str(parsed)}

        try:
            stored = store_upload(data, settings, datetime.now(UTC), hint=parsed)
        except StoreError as e:
            raise HTTPException(status_code=e.status, detail=str(e)) from e

        return JSONResponse(
            status_code=200 if stored.duplicate else 201,
            content={
                "sha256": stored.sha256,
                "stored_as": stored.stored_as,
                "size": stored.size,
                "duplicate": stored.duplicate,
            },
        )

    @app.get("/api/inbox/stats")
    def get_stats(_claims: Annotated[dict, Depends(require_access)]) -> dict:
        stats = inbox_stats(settings.inbox)
        return {"count": stats.count, "oldest": stats.oldest}

    return app


def main() -> None:  # pragma: no cover - コンテナの入口
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8081)  # noqa: S104


if __name__ == "__main__":  # pragma: no cover
    main()
