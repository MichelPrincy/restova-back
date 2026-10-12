"""Format d'erreur unique : {"error": {"code", "message", "details"?}}"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("restova")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


class CodedValueError(ValueError):
    """Erreur de validation Pydantic portant un code du contrat (INVALID_EMAIL, WEAK_PASSWORD...)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def unauthorized(message: str = "Session invalide ou expirée.") -> AppError:
    return AppError(401, "UNAUTHORIZED", message)


def not_found(message: str = "Ressource introuvable.") -> AppError:
    return AppError(404, "NOT_FOUND", message)


def validation_error(message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError(400, "VALIDATION_ERROR", message, details)


def too_many_requests() -> AppError:
    return AppError(429, "TOO_MANY_REQUESTS", "Trop de tentatives. Réessayez dans quelques instants.")


def error_response(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


_TYPE_MESSAGES = {
    "missing": "Champ obligatoire.",
    "string_too_short": "Ce champ ne peut pas être vide.",
    "string_too_long": "Texte trop long.",
    "string_type": "Une chaîne de caractères est attendue.",
    "int_type": "Un nombre entier est attendu.",
    "int_parsing": "Un nombre entier est attendu.",
    "float_type": "Un nombre est attendu.",
    "float_parsing": "Un nombre est attendu.",
    "decimal_type": "Un nombre est attendu.",
    "decimal_parsing": "Un nombre est attendu.",
    "bool_type": "Une valeur vrai/faux est attendue.",
    "bool_parsing": "Une valeur vrai/faux est attendue.",
    "list_type": "Une liste est attendue.",
    "literal_error": "Valeur non autorisée.",
    "json_invalid": "Corps JSON invalide.",
    "greater_than": "Valeur hors limites.",
    "greater_than_equal": "Valeur hors limites.",
    "less_than": "Valeur hors limites.",
    "less_than_equal": "Valeur hors limites.",
    "too_short": "Liste trop courte.",
    "too_long": "Liste trop longue.",
}


def _field_name(loc: tuple) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) or "body"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details: dict[str, str] = {}
        coded: CodedValueError | None = None
        for err in exc.errors():
            inner = (err.get("ctx") or {}).get("error")
            if isinstance(inner, CodedValueError):
                message = inner.message
                # INVALID_EMAIL / WEAK_PASSWORD prennent le pas sur VALIDATION_ERROR
                if coded is None or (coded.code == "VALIDATION_ERROR" and inner.code != "VALIDATION_ERROR"):
                    coded = inner
            else:
                message = _TYPE_MESSAGES.get(err.get("type", ""), "Valeur invalide.")
            details.setdefault(_field_name(tuple(err.get("loc", ()))), message)

        code = coded.code if coded else "VALIDATION_ERROR"
        if len(details) == 1:
            message = next(iter(details.values()))
        else:
            message = "Certains champs sont invalides."
        if coded and coded.code != "VALIDATION_ERROR":
            message = coded.message
        return error_response(400, code, message, details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        mapping = {
            401: ("UNAUTHORIZED", "Session invalide ou expirée."),
            403: ("FORBIDDEN", "Accès refusé."),
            404: ("NOT_FOUND", "Ressource introuvable."),
            405: ("METHOD_NOT_ALLOWED", "Méthode non autorisée."),
        }
        code, message = mapping.get(exc.status_code, ("HTTP_ERROR", "Requête invalide."))
        return error_response(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Erreur non gérée", exc_info=exc)
        return error_response(500, "INTERNAL_ERROR", "Une erreur interne est survenue.")
