{
    'name': 'Extensión de Activos - Préstamos',
    'version': '18.0.1.0.0',
    'summary': 'Agrega campos para registrar préstamos en activos fijos',
    'category': 'Accounting',
    'author': 'Ateneo Lab',
    'license': 'LGPL-3',
    'depends': ['base', 'account_asset'],
    'data': [
        'views/account_asset_views.xml',
    ],
    'installable': True,
    'application': False,
}
