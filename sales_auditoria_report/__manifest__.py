# -*- coding: utf-8 -*-
{
    "name": "Reporte de Ventas Auditoría",
    "version": "1.0",
    "summary": (
        "Agrega un wizard para generar Reporte de Ventas para Auditores"
    ),
    "description": """
Reporte de Ventas Auditoría
==========================
- Wizard para seleccionar período (fecha inicio - fecha fin).
- Excluye facturas en estado 'borrador' y 'cancelado'.
- Incluye facturas rectificativas (con valores en negativo).
- Agrupa por Tipo de Comprobante en el orden:
    1. Credito Fiscal
    2. Notas de Credito
    3. Factura Gubernamental
    4. Factura Régimen Especial
    5. Pesos(Conversion)
- Al final de cada grupo, subtotaliza importes.
- Exporta a PDF (QWeb) y a Excel (.xlsx).
- Encabezado:
    Reporte Ventas Auditores
       [Periodo seleccionado, alineado a la derecha]
       Moneda <valor> Pesos RD (alineado a la derecha)
    Campos: No. Factura, Fecha, Cliente, Ingreso Neto, ITBIS, Total, NCF.
""",
    "author": "Ateneo Lab",
    "depends": [
        "account",
        "base",  # para la moneda y QWeb
        "web",           # para QWeb‐PDF
        "account_reports"
    ],
    "data": [
        # Primero cargamos la ACL del wizard
        "security/ir.model.access.csv",
        # Luego el wizard y su menú
        "views/wizard_sales_auditoria_views.xml",
        "views/menu_sales_auditoria.xml",
        "report/report_sales_auditoria_templates.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            # Si necesitas CSS/JS adicionales para el PDF, agrégalos aquí.
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
