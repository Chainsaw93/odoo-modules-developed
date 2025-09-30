# -*- coding: utf-8 -*-
{
    'name': "Hr Payroll Provision Management",
    'description': """
        Hr Payroll Provision Management for XIII and XIV
    """,
    'summary': "Manage XIII provisions in payroll",
    'author': "Javier <javier@ateneolab.com>",
    'website': "http://www.ateneolab.com",
    'category': 'Human Resources/Payroll',
    'version': '18.0.1.0.0',
    'depends': [
        'base', 
        'hr_contract', 
        'hr_work_entry_contract', 
        'hr_xiii'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/hr_provision_view.xml',
        'views/hr_contract_ext_view.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}