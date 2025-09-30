{
    'name': 'Integración de Costos Indirectos en Fabricación',
    'version': '18.0.1.0.0',
    'summary': 'Muestra y suma los costos indirectos (Landed Costs) en el análisis de costos de las Órdenes de Fabricación.',
    'author': 'Tu Nombre/Empresa',
    'category': 'Manufacturing/Inventory',
    'license': 'LGPL-3',
    'depends': [
        'mrp_landed_costs', # Dependencia clave para asegurar la funcionalidad
    ],
    'data': [
        'views/report_mrp_production_cost.xml',
    ],
    'installable': True,
    'application': False,
}