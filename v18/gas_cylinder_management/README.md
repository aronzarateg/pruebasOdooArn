# Gestión de Gases y Cilindros — Odoo 18 Enterprise

## Estado
Prototipo técnico **NO validado en instancia Odoo**. No usar en producción.

## Instalación
Agregar esta carpeta raíz al `addons_path`; actualizar aplicaciones; instalar `gas_cylinder_base`, después `gas_cylinder_stock`.

## Funciones disponibles
- Catálogo de cilindros y series (`gas_cylinder_base`).
- Campos `lot_supplier` y `code_supplier` en `stock.lot`.
- Estructura de contenido y consulta de saldos, inicialmente vacíos.
- Configuración de ubicaciones, borradores de operaciones y consulta de kardex, inicialmente vacío.

## No implementado / bloqueado a propósito
- No crea ni valida `stock.picking`, `stock.move` o `stock.move.line`.
- No registra gas ni altera `stock.quant`; no genera contabilidad.
- No actualiza automáticamente lote/código proveedor: depende de la recepción validada en el módulo purchase futuro.
- El método `action_done` y creación del kardex están bloqueados para impedir inconsistencias.
- `purchase`, `sale` y `rental` son carpetas de planificación, no addons instalables.

## Antes de probar
Revisar vistas y reglas de seguridad en Odoo 18 real, configurar grupos y validar unidades de medida, propiedad de cilindros, compañías y escenarios de stock. La configuración por `stock.location` no crea ubicaciones.
