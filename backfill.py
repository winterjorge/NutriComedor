#!/usr/bin/env python3
"""
Script de Backfill para el Scraper Modularizado de NutriComedor
Ejecuta el scraper para un rango de fechas histórico.
"""

import subprocess
import sys
import time
import os
from datetime import date, timedelta
from pathlib import Path

# ==========================================
# CONFIGURACIÓN
# ==========================================
# Define tu rango de fechas aquí
FECHA_INICIO = date(2026, 4, 1)
FECHA_FIN = date(2026, 7, 13)

# Pausa entre ejecuciones (segundos)
# Importante para no saturar al servidor MIDAGRI
PAUSA_SEGUNDOS = 5

# Directorio del backend (donde está la carpeta scraper/)
BACKEND_DIR = Path(__file__).parent / "backend"

# ==========================================
def ejecutar_backfill():
    """
    Ejecuta el scraper para cada fecha en el rango definido.
    """
    print("=" * 70)
    print("BACKFILL DE PRECIOS SISAP - NutriComedor")
    print("=" * 70)
    print(f"Fecha Inicio: {FECHA_INICIO.strftime('%Y-%m-%d')}")
    print(f"Fecha Fin:    {FECHA_FIN.strftime('%Y-%m-%d')}")
    print(f"Pausa:        {PAUSA_SEGUNDOS} segundos")
    print("=" * 70)
    
    # Verificar que el directorio backend exista
    if not BACKEND_DIR.exists():
        print(f"[ERROR] Directorio backend no encontrado: {BACKEND_DIR}")
        sys.exit(1)
    
    # Verificar que el scraper exista
    scraper_dir = BACKEND_DIR / "scraper"
    if not scraper_dir.exists():
        print(f"[ERROR] Directorio scraper no encontrado: {scraper_dir}")
        sys.exit(1)
    
    fecha_actual = FECHA_INICIO
    total_dias = (FECHA_FIN - FECHA_INICIO).days + 1
    dia_actual = 1
    
    exitos = 0
    fallos = 0
    
    while fecha_actual <= FECHA_FIN:
        fecha_str = fecha_actual.strftime("%Y-%m-%d")
        
        print(f"\n[{dia_actual}/{total_dias}] Procesando fecha: {fecha_str}...")
        
        try:
            # Ejecutar el scraper modularizado
            # Usamos python -m scraper.main desde el directorio backend
            resultado = subprocess.run(
                [sys.executable, "-m", "scraper.main", "--fecha", fecha_str],
                cwd=str(BACKEND_DIR),  # Directorio de trabajo
                check=True,
                capture_output=False  # Mostrar output en tiempo real
            )
            
            print(f"[✓] Fecha {fecha_str} completada exitosamente.")
            exitos += 1
            
        except subprocess.CalledProcessError as e:
            print(f"[✗] ERROR: Falló la ejecución para {fecha_str}")
            print(f"    Código de error: {e.returncode}")
            fallos += 1
            
        except Exception as e:
            print(f"[✗] ERROR INESPERADO para {fecha_str}: {str(e)}")
            fallos += 1
        
        # Pausa para ser amables con el servidor remoto
        # (excepto en la última iteración)
        if fecha_actual < FECHA_FIN:
            time.sleep(PAUSA_SEGUNDOS)
        
        fecha_actual += timedelta(days=1)
        dia_actual += 1
    
    # ==========================================
    # RESUMEN FINAL
    # ==========================================
    print("\n" + "=" * 70)
    print("RESUMEN DE BACKFILL")
    print("=" * 70)
    print(f"Total fechas procesadas: {total_dias}")
    print(f"Exitosas:  {exitos} ✓")
    print(f"Fallidas:  {fallos} ✗")
    print(f"Tasa éxito: {(exitos/total_dias*100):.1f}%")
    print("=" * 70)
    
    if fallos > 0:
        print("\n[ADVERTENCIA] Algunas fechas fallaron. Revisa los logs arriba.")
        sys.exit(1)
    else:
        print("\n[ÉXITO] Todas las fechas se procesaron correctamente.")
        sys.exit(0)

# ==========================================
if __name__ == "__main__":
    try:
        ejecutar_backfill()
    except KeyboardInterrupt:
        print("\n\n[INTERRUPCIÓN] Proceso cancelado por el usuario (Ctrl+C)")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR CRÍTICO] {str(e)}")
        sys.exit(1)