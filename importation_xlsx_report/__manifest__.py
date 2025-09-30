{
    "name": "Informe Resumido de Importación (XLSX)",
    "version": "1.0",
    "author": "Ateneo Lab",
    "category": "Importaciones",
    "license": "LGPL-3",
    "summary": "Añade un botón para generar un Informe Resumido de Importación en formato Excel",
    "description": """
Este módulo extiende `importation_reports` y agrega:
1) Botón en el formulario de importación (solo en estado 'done').
2) Método `generate_xlsx_summary_report` que genera un archivo XLSX con:
   - Logo y nombre de la compañía
   - Identificador de la importación
   - Texto de moneda ("VALORES EN …")
   - Fecha de liquidación
   - Tabla "Ítems de liquidación" (solo `is_landed_cost=True`)
   - Tabla "Proveedores" (unicidad de proveedores de todas las compras)
   - Tabla "Productos" (tomados de `trade.costo_details`)
   - Tabla "Descripción" (ITBIS y Gravamen)
""",
    "depends": [
        "importation_reports",
        "base",
    ],
    "data": [
        'security/ir.model.access.csv',
        'views/trade_importation_views.xml',
        'views/importation_report_wizard_views.xml',
    ],
    "installable": True,
    "application": False,
    'images': ['static/description/icon.png'],
    "auto_install": False,
}
