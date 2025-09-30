{
    'name': 'Barcode Operations Extension',
    'version': '18.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Display origin and orden_compra fields in barcode operations',
    'description': """
    This module extends the barcode operations view to display:
    - Document origin field (stock.picking.origin)
    - Purchase Order field (stock.picking.orden_compra)
    
    Features:
    - Uses existing fields from stock.picking model
    - Consistent styling with existing UI elements
    - Enhanced picking information display in barcode interface
    """,
    'depends': [
        'stock',
        'stock_barcode',
        'barcodes',
        'stock_picking_extra_fields',
    ],
    'data': [
        'views/barcode_operations_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'barcode_operations_extension/static/src/css/barcode_operations_extension.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}