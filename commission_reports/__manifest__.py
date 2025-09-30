# -*- coding: utf-8 -*-

{
    'name': 'Reporte de Comisiones Gadint',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Reporting',
    'summary': 'Reporte detallado de ventas para cálculo de comisiones con costos',
    'description': """
Reporte de Comisiones
=====================

Este módulo proporciona un reporte completo de ventas con cálculo detallado 
de costos y márgenes para el pago de comisiones.

Características principales:
---------------------------
* Wizard con filtros avanzados (fechas, vendedores, clientes, categorías, etc.)
* Cálculo automático de costos, beneficios y márgenes
* Opciones de agrupación flexibles
* Exportación a PDF y Excel
* Formato optimizado para impresión A4 horizontal
* Totales y subtotales automáticos

Campos del reporte:
------------------
* Cliente, Fecha, Factura, Categoría, Código, Descripción
* Moneda, Unidad, Cantidad, Costo, Costo Total
* Precio, Total Neto, Beneficio, % Margen Neto

Filtros disponibles:
-------------------
* Rango de fechas
* Vendedores (selección múltiple)
* Clientes (selección múltiple)
* Categorías de productos (selección múltiple)
* Productos específicos (selección múltiple)
* Números de factura
* Sucursales/Empresas
* Almacenes

Opciones de agrupación:
----------------------
* Por Vendedor
* Por Cliente
* Por Categoría
* Por Producto
* Por Sucursal
* Por Almacén
    """,
    'author': 'Ateneo Lab',
    'website': 'https://www.ateneolab.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'product',
        'stock',
        'sale',
        'report_xlsx',  # Para reportes Excel
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/commission_report_wizard_views.xml',
        'reports/commission_report_templates.xml',
        'reports/commission_report_actions.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'external_dependencies': {
        'python': ['xlsxwriter'],  # Para generar archivos Excel
    },
}