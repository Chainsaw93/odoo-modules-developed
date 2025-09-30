{
    'name': 'Purchase Warranty',
    'version': '18.0.1.0.0',
    'category': 'Purchase',
    'summary': 'Adds warranty purchase functionality to purchase orders and vendor bills',
    'description': """
Purchase Warranty
=================
Este módulo agrega la funcionalidad de "Compra por garantía" que permite:

1. Marcar una orden de compra como "Compra por garantía"
2. Automáticamente usar el tipo de operación de "Garantía" para la recepción
3. Heredar el campo en las facturas de proveedor creadas desde la orden de compra

Características:
- Campo booleano "Compra por garantía" en órdenes de compra
- Solo editable en estados "Solicitud de cotización" y "Solicitud de cotización enviada"
- Herencia automática del campo en facturas de proveedor
- Integración con tipos de operación de garantía
    """,
    'author': 'Javier',
    'website': 'https://www.ateneolab.com',
    'depends': ['purchase', 'account', 'stock', 'stock_reception_type'],
    'data': [
        'views/purchase_order_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}