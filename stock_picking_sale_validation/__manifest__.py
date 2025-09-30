{
    'name': 'Stock Picking Sale Validation',
    'version': '1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Validación de productos en entregas basadas en órdenes de venta',
    'description': 'Este módulo agrega validaciones para stock.picking de tipo entrega',
    'author': 'Ateneo Lab',
    'website': 'https://www.ateneolab.com',
    'depends': ['stock', 'sale_stock', 'stock_barcode'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_picking_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_picking_sale_validation/static/src/js/barcode_validation.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}