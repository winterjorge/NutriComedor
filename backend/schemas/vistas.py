"""
schemas/vistas.py
Objetivo: Modelos Pydantic del editor de permisos por vistas: reemplazo del conjunto
          de módulos permitidos para un rol (la matriz se edita desde la sub-pestaña
          Vistas del panel de administración).
Uso: Importar en routers/vistas.py para validar el payload de actualización.
Referencia: ticket COM-25 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
from pydantic import BaseModel
from typing import List


class PermisosRolUpdate(BaseModel):
    """
    Reemplaza el conjunto de módulos permitidos de un rol por la lista enviada.
    `modulo_ids` vacío deja al rol sin módulos asignados.
    """
    modulo_ids: List[int]
    usuario_solicitante_id: int