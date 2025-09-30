# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    # XIII Configuration fields
    xiii_init_date = fields.Date(
        'XIII Start Date',
        default='2024-12-01',
        help="Start date for XIII salary calculation period"
    )
    xiii_end_date = fields.Date(
        'XIII End Date', 
        default='2025-11-30',
        help="End date for XIII salary calculation period"
    )
    xiii_pay_date = fields.Date(
        'XIII Payment Date',
        default='2025-12-25', 
        help="Date when XIII salary should be paid"
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # XIII Configuration fields (related to company)
    xiii_init_date = fields.Date(
        'XIII Start Date',
        related='company_id.xiii_init_date',
        readonly=False,
        help="Start date for XIII salary calculation period"
    )
    xiii_end_date = fields.Date(
        'XIII End Date',
        related='company_id.xiii_end_date', 
        readonly=False,
        help="End date for XIII salary calculation period"
    )
    xiii_pay_date = fields.Date(
        'XIII Payment Date',
        related='company_id.xiii_pay_date',
        readonly=False,
        help="Date when XIII salary should be paid"
    )

    @api.model
    def _setup_default_xiii_config(self):
        """Setup default XIII configuration for companies that don't have it"""
        companies = self.env['res.company'].search([
            '|', '|',
            ('xiii_init_date', '=', False),
            ('xiii_end_date', '=', False), 
            ('xiii_pay_date', '=', False)
        ])
        
        for company in companies:
            if not company.xiii_init_date:
                company.xiii_init_date = '2024-12-01'
            if not company.xiii_end_date:
                company.xiii_end_date = '2025-11-30'
            if not company.xiii_pay_date:
                company.xiii_pay_date = '2025-12-25'