{
    'name': 'Stock Lot Filter Available',
    'version': '1.0',
    'depends': ['stock','product'],
    'author': 'Ateneo Lab',
    'category': 'Inventory',
    'description': '''
        Muestra solo los números de serie con stock disponible en entregas y transferencias internas.
    ''',
    'data': [
        'views/stock_move_line_views.xml',
    ],
    'installable': True,
    'application': False,
    'images': ['static/description/icon.png'],
}
