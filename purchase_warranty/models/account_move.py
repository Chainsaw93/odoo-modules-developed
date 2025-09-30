from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    warranty_purchase = fields.Boolean(
        string='Compra por garantía',
        default=False,
        help='Indica si esta factura corresponde a una compra por garantía'
    )

    @api.model
    def create(self, vals):
        """
        Override del método create para heredar el campo warranty_purchase
        desde la orden de compra cuando se crea la factura
        """
        # Si se está creando desde una orden de compra
        if 'purchase_id' in vals and vals.get('purchase_id'):
            purchase_order = self.env['purchase.order'].browse(vals['purchase_id'])
            if purchase_order.warranty_purchase:
                vals['warranty_purchase'] = True

        # Verificar también si viene desde invoice_origin que contenga una orden de compra
        elif 'invoice_origin' in vals and vals.get('invoice_origin'):
            # Buscar orden de compra por el campo origin
            purchase_orders = self.env['purchase.order'].search([
                ('name', '=', vals['invoice_origin'])
            ])
            if purchase_orders and purchase_orders[0].warranty_purchase:
                vals['warranty_purchase'] = True

        return super().create(vals)

    def _get_invoice_reference(self):
        """
        Heredar información de la orden de compra al crear la factura
        """
        result = super()._get_invoice_reference()
        
        # Si existe una orden de compra relacionada, heredar el campo warranty_purchase
        if self.purchase_id and self.purchase_id.warranty_purchase:
            self.warranty_purchase = True
            
        return result

    @api.onchange('purchase_id')
    def _onchange_purchase_id(self):
        """
        Actualizar el campo warranty_purchase cuando se selecciona una orden de compra
        """
        if self.purchase_id:
            self.warranty_purchase = self.purchase_id.warranty_purchase
