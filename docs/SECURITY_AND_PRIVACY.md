# Seguridad y privacidad

## Principios

- No acusar directamente a personas: usar lenguaje de riesgo y evidencia.
- Minimizar datos personales.
- Registrar auditoria de cada accion sensible.
- Separar permisos por rol.
- Validar toda entrada.

## Controles transversales

- Input validation contra XSS, SQLi e IDOR.
- Rate limit por IP usando Redis.
- EXIF stripping para evidencia subida: JPEG, PNG y WebP se limpian durante upload antes de calcular hash y almacenar.
- Audit log de acciones administrativas.
- Revision humana para estados sensibles.
- Retencion limitada de evidencia y datos personales.

## Ley 29733 - Peru

El sistema debe tratar datos personales con finalidad clara, minimizacion, acceso controlado y trazabilidad. Antes de produccion debe pasar revision legal.
