{
    'name': 'Costo en Destino de Fabricación',
    'version': '18.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Añade campo booleano para costo en destino de fabricación',
    'description': """
        Este módulo añade un campo booleano "Costo en destino de fabricación" 
        en la ficha del producto que solo se muestra cuando "Es un costo en destino" es verdadero.
    """,
    'author': 'Ateneo Lab',
    'website': 'https://www.ateneolab.com',
    'depends': [
        'base',
        'product',
        'stock_landed_costs',
    ],
    'data': [
        'views/product_template_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}