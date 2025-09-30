{
    'name': 'Asset Responsible Tracking',
    'version': '1.0',
    'category': 'Accounting',
    'summary': 'Gestión de responsables de activos fijos',
    'depends': [
        'account_asset', 
        'hr',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/account_asset_view.xml',
    ],
    'installable': True,
    'application': False,
}
