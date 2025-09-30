# -*- coding: utf-8 -*-
{
    'name': 'XIII for Payroll',
    'version': '18.0.1.0.0',
    'summary': 'XIII salary calculation for payroll',
    'description': """
        XIII Salary Management
        ======================
        
        This module provides XIII salary calculation functionality including:
        * XIII accumulation configuration
        * Monthly XIII calculation
        * XIII period management
        * Integration with payroll rules
    """,
    'category': 'Human Resources/Payroll',
    'author': "Javier <javier@ateneolab.com>",
    'website': "http://www.ateneolab.com",
    'sequence': 1,
    'depends': [
        'hr_payroll', 
        'hr_payslip_historic_income'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/xiii_defaults.xml',
        'data/payroll_rule_data.xml',
        'views/contract_ext.xml',
        'views/res_config_settings.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}