{
    'name': 'Costos Indirectos en Fabricación',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Gestión automática de costos indirectos en órdenes de fabricación',
    'description': """
        Este módulo automatiza la creación y gestión de costos en destino para órdenes de fabricación:
        - Crea automáticamente costos en destino al confirmar órdenes de fabricación
        - Agrega tab de costos indirectos en órdenes de fabricación con modelo proxy
        - Permite gestión manual de líneas de costos indirectos
        - Valida costos antes de cerrar la producción
        - Sincronización bidireccional entre líneas proxy y landed cost
    """,
    'author': 'Ateneo Lab',
    'website': 'https://www.ateneolab.com',
    'depends': [
        'base',
        'mrp',
        'stock_landed_costs',
        'mrp_landed_costs',
        'custom_landed_cost_manufacturing',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/production_close_confirmation_views.xml',
        'views/mrp_production_cost_line_views.xml',
        'views/mrp_production_views.xml',
        'views/stock_landed_cost_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}