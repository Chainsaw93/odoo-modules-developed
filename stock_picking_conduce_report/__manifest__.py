{
    'name': 'Stock Picking Conduce Report',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Custom Conduce report for stock picking operations',
    'description': """
        Custom module that adds a new 'Conduce' report option for stock picking operations.
        Features:
        - New print option 'Conduce' as first option in print menu
        - Groups products with serial tracking into single lines
        - Shows serial numbers and lots under product description
        - Custom column layout: Cantidad, Referencia, Descripción, Notas
        - Repeats table headers on every page
    """,
    'author': 'Custom Development',
    'depends': ['stock','stock_picking_responsable','stock_picking_extra_fields'],
    'data': [
        'report/stock_picking_conduce_report.xml',
        'report/stock_picking_conduce_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}