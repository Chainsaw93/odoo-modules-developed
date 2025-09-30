# -*- coding: utf-8 -*-
{
    'name': 'XIV for Payroll',
    'version': '18.0.1.0.0',
    'summary': 'XIV salary calculation for payroll',
    'description': """
        XIV Salary Management
        =====================
        
        This module provides XIV salary calculation functionality including:
        * XIV accumulation configuration
        * SBU-based XIV calculation
        * XIV period management
        * Integration with payroll rules
        * Automatic provision tracking
    """,
    'category': 'Human Resources/Payroll',
    'author': 'Javier Rodriguez <javier@ateneolab.com>',
    'website': 'http://www.ateneolab.com',
    'sequence': 1,
    'depends': [
        'hr_payroll', 
        'hr_job_regime_base'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/payroll_rule_data.xml',
        'views/contract_ext.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}