# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_payslip_done(self):
        """
        Override to handle XIV accumulation when payslip is confirmed.
        
        When payslip contains:
        - XIV-A (XIV Accumulated): Reset accumulated amount to 0
        - XIV-P (XIV Provision): Add provision amount to accumulated total
        """
        result = super().action_payslip_done()
        
        for payslip in self:
            if not payslip.contract_id:
                continue
                
            xiv_accumulated = 0.0
            xiv_provision = 0.0
            
            # Process XIV-related payslip lines
            for line in payslip.line_ids:
                if line.code == 'XIV-A':
                    # XIV payment made - reset accumulated amount
                    xiv_accumulated = 0.0
                    payslip.contract_id.accumulated_xiv_amount = 0.0
                    
                elif line.code == 'XIV-P':
                    # XIV provision - add to accumulated amount
                    xiv_provision += line.amount
                    
            # Update accumulated XIV amount with provisions
            if xiv_provision > 0.0:
                current_accumulated = payslip.contract_id.accumulated_xiv_amount or 0.0
                new_accumulated = current_accumulated + xiv_provision
                payslip.contract_id.accumulated_xiv_amount = new_accumulated
                
        return result