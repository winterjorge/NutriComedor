import unicodedata

def normalizar_nombre(texto):
    """
    Normaliza el texto eliminando tildes pero preservando la ñ.
    Retorna el texto en formato capitalize.
    """
    if not texto:
        return ""
    
    # Proteger la ñ temporalmente
    texto_protegido = texto.replace('ñ', 'enie').replace('Ñ', 'ENIE')
    
    # Eliminar tildes
    texto_sin_tildes = ''.join(
        c for c in unicodedata.normalize('NFD', texto_protegido)
        if unicodedata.category(c) != 'Mn'
    )
    
    # Restaurar la ñ
    texto_restaurado = texto_sin_tildes.replace('enie', 'ñ').replace('ENIE', 'Ñ')
    
    return texto_restaurado.strip().capitalize()

def formatear_precio(valor):
    """
    Convierte un string de precio a float redondeado a 2 decimales.
    """
    try:
        # Remover comas y espacios
        valor_limpio = str(valor).replace(',', '').strip()
        return round(float(valor_limpio), 2)
    except (ValueError, TypeError):
        return 0.0