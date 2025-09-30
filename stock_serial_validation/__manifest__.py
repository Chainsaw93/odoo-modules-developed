{
    'name': 'Stock Serial Number Unified Validation',
    'version': '18.0.2.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Unified serial number validation for all stock contexts',
    'description': """
        Validación unificada de números de serie que funciona en:
        - Formularios de stock.picking
        - Diálogos de movimiento de stock (Abrir: Movimiento de stock)
        - Aplicación de código de barras
        - Operaciones detalladas
        
        Características:
        - Servicio central de validación
        - Validación en tiempo real con campos computados
        - Prevención de duplicados en mismo picking
        - Validación cruzada para entregas pendientes
        - Manejo robusto de errores con mensajes en español
    """,
    'author': 'Tu Empresa',
    'depends': ['stock', 'stock_barcode'],
    'data': [
        'security/ir.model.access.csv',
        'data/stock_data.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}