{
    'name': 'Serial Number Validation',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Validación en tiempo real de números de serie para operaciones de stock',
    'description': """
        Módulo para validación de números de serie en tiempo real:
        - Previene duplicados dentro del mismo picking
        - Valida disponibilidad para entregas
        - Soporte para aplicación de códigos de barras
        - Validaciones específicas por tipo de operación
    """,
    'author': 'Ateneo Lab',
    'website': 'https://www.ateneolab.com',
    'depends': [
        'base',
        'stock',
        'barcodes',
        'stock_barcode',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_picking_views.xml',
        'views/stock_move_line_views.xml',
        'data/serial_validation_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'serial_number_validation/static/src/css/serial_validation.css',
            'serial_number_validation/static/src/js/serial_validation_field.js',
            'serial_number_validation/static/src/js/barcode_integration.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}