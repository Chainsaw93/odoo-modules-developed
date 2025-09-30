{
    'name': 'MRP Landed Cost Integration Module',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'BOM Overview button in Manufacturing Orders with MO Overview data',
    'description': """
        Adds a smart button "BOM Overview" to Manufacturing Orders that displays
        MO Overview data using the same visual format as the standard BOM Overview.
    """,
    'depends': ['mrp'],
    'data': [
        'views/mrp_production_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mo_bom_overview/static/src/css/mo_bom_overview.css',
            'mo_bom_overview/static/src/js/mo_bom_overview.js',
            'mo_bom_overview/static/src/xml/mo_bom_overview.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}