# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.onchange('partner_id')
    def _onchange_check_partner_loans(self):
        """
        Muestra una notificación si el cliente seleccionado tiene productos en préstamo
        """
        if self.partner_id:
            # Buscar préstamos activos del cliente
            active_loans = self.env['loan.tracking.detail'].search([
                ('picking_id.loaned_to_partner_id', '=', self.partner_id.id),
                ('status', 'in', ['active', 'pending_resolution'])
            ])

            if active_loans:
                # Agrupar productos por nombre y cantidad
                loan_summary = []
                for loan in active_loans:
                    loan_summary.append(
                        f"(Préstamo: {loan.picking_id.name})"
                        f"{loan.product_id.name}: {loan.quantity} {loan.product_id.uom_id.name} "
                    )

                # Construir mensaje
                message = "El cliente tiene los siguientes productos en préstamo:\n• "
                message += "\n• ".join(loan_summary)

                # Retornar un warning que se mostrará como notificación
                return {
                    'warning': {
                        'title': '⚠️ Productos en Préstamo',
                        'message': message,
                    }
                }
