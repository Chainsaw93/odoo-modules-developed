# -*- coding: utf-8 -*-
{
    'name': 'Comisiones Gadint',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Sistema de comisiones personalizado para vendedores externos de Gadint',
    'description': '''
        Módulo personalizado para el manejo de comisiones de vendedores externos en Gadint.
        
        Características principales:
        - Campo booleano para identificar equipo de vendedores externos en contactos
        - Gestión de vendedores externos con tipos (Líder/Vendedor)
        - Compatible con sistema de comisiones nativo de Odoo 18.0
        - Campos en cotizaciones y facturas para asignar vendedores externos
        - Automatización de comisiones pagadas basada en pagos de facturas
        - Sincronización entre pedidos y facturas
        - Sistema de seguimiento con chatter para vendedores externos
        
        NOTA: Odoo 18.0 incluye sistema de comisiones nativo. Active desde:
        Ventas → Configuración → Ajustes → Comisiones
    ''',
    'author': 'Javier',
    'website': 'https://www.ateneolab.com',
    'depends': [
        'base',
        'mail',  
        'sale',
        'account',
        'sale_commission',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/commission_data.xml',
        'views/res_partner_views.xml',
        'views/external_salesperson_views.xml', 
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'views/commission_plan_views.xml',
        'views/commission_achievements_views.xml',
        'views/menus.xml',
        'views/settings_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}