import time

from fastapi import HTTPException, Request

# Limitador por IP en memoria: suficiente para un solo proceso/MVP. Si en el
# futuro se corre con varios workers/replicas habria que mover esto a un
# almacen compartido (Redis, etc), porque cada proceso llevaria su propio
# conteo y el limite real seria N veces mayor al configurado.
_peticiones: dict[str, list[float]] = {}


def _ip_de(request: Request) -> str:
    return request.client.host if request.client else "desconocido"


def limitar(limite: int, ventana_segundos: int):
    """Fabrica de dependencias de FastAPI: `Depends(limitar(120, 60))`
    permite como maximo `limite` peticiones por IP cada `ventana_segundos`."""

    def dependencia(request: Request) -> None:
        ip = _ip_de(request)
        clave = f"{ip}:{limite}:{ventana_segundos}"
        ahora = time.monotonic()

        vigentes = [t for t in _peticiones.get(clave, []) if ahora - t < ventana_segundos]
        if len(vigentes) >= limite:
            raise HTTPException(status_code=429, detail="Demasiadas peticiones, intenta de nuevo en un momento")

        vigentes.append(ahora)
        _peticiones[clave] = vigentes

    return dependencia
