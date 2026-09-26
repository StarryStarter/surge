# app/api/errors.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import (
    InvalidTransition,
    PoolNotFound,
    PoolSoldOut,
    ReservationNotFound,
)

_STATUS = {
    PoolNotFound: 404,        # "we couldn't find what you asked for"
    ReservationNotFound: 404,
    PoolSoldOut: 409,         # "your request is valid, but it conflicts with reality"
    InvalidTransition: 409,
}


def register(app: FastAPI) -> None:
    for exc_type, status_code in _STATUS.items():

        def handler(
            request: Request, exc: Exception, status_code: int = status_code
        ) -> JSONResponse:
            return JSONResponse(status_code=status_code, content={"detail": str(exc)})

        app.add_exception_handler(exc_type, handler)