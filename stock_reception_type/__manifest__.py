{
    'name': 'Stock Reception Type',
    'version': '18.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Adds reception operation type field to stock picking types',
    'description': """
Stock Reception Type
====================
Este módulo agrega un campo de selección "Tipo de operación de recepción" 
a los tipos de operaciones de inventario. El campo solo se muestra cuando 
el tipo de operación es de Recepción.

Características:
- Campo de selección con opción "Garantía"
- No obligatorio
- Solo visible para operaciones de tipo Recepción
    """,
    'author': 'Javier',
    'website': 'https://www.ateneolab.com',
    'depends': ['stock'],
    'data': [
        'views/stock_picking_type_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}