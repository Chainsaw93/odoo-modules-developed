{
    'name': 'Stock Picking Responsable',
    'version': '1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Agrega campo Responsable a stock.picking que se completa automáticamente al validar',
    'description': 'Este módulo agrega un campo "Responsable" al modelo stock.picking',
    'author': 'Ateneo Lab',
    'website': 'https://www.ateneolab.com',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
