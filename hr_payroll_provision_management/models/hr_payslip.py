from odoo import fields, models, api, _


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_payslip_done(self):
        """Override to handle provision creation/payment when payslip is confirmed"""
        result = super().action_payslip_done()
        
        for payslip in self:
            for line in payslip.line_ids:
                # Handle XIII Accumulated payment - marks existing provisions as paid
                if line.code == 'XIII-A' and line.amount > 0:
                    provisions = payslip.contract_id.get_pending_provision_xiii()
                    if provisions:
                        provisions.write({"state": "paid"})
                        # Log the payment
                        payslip.message_post(
                            body=_("XIII provisions marked as paid: %s provisions totaling %s") % 
                                 (len(provisions), sum(provisions.mapped('provision_amount')))
                        )
                    
                # Handle XIII Provision creation - creates new provision record
                elif line.code == 'XIII-P' and line.amount > 0:
                    provision = payslip.contract_id.create_provision_xiii(
                        line.amount, 
                        payslip.date_to, 
                        f"XIII Provision from payslip {payslip.name}"
                    )
                    # Log the provision creation
                    payslip.message_post(
                        body=_("XIII provision created: %s for amount %s") % 
                             (provision.name, line.amount)
                    )
                    
                # Handle Monthly XIII - no provision logic needed, just payment
                elif line.code == 'XIII' and line.amount > 0:
                    # This is monthly XIII payment, no provision management needed
                    payslip.message_post(
                        body=_("Monthly XIII payment processed: %s") % line.amount
                    )
                    
        return result