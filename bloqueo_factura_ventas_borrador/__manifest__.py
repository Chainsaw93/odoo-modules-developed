{
    'name': 'Bloqueo Factura Ventas Borrador',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Control de facturas borrador',
    'depends': ['base', 'account', 'sale'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}