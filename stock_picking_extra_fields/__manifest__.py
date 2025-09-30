{
    'name': 'Stock Picking Extra Fields',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Extensión del stock.picking con campos de condición y vía',
    'description': """
        Este módulo extiende el modelo stock.picking agregando:
        - Campo Condición (obligatorio)
        - Campo Vía (obligatorio)
        - Campo Orden de compra (no editable, desde sale.order)
    """,
    'author': 'Ateneo Lab',
    'website': 'https://www.ateneolab.com',
    'depends': [
        'stock',
        'sale_stock',
    ],
    'data': [
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}