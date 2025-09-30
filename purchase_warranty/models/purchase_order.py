from odoo import models, fields, api
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    warranty_purchase = fields.Boolean(
        string='Compra por garantía',
        default=False,
        help='Marca esta orden como una compra por garantía. '
             'Esto hará que se use el tipo de operación de garantía para la recepción.',
        readonly=True,
        states={'draft': [('readonly', False)], 'sent': [('readonly', False)]}
    )

    def _create_picking(self):
        """
        Override del método que crea las operaciones de recepción
        para usar el tipo de operación de garantía cuando corresponda
        """
        # Si no es compra por garantía, usar comportamiento estándar
        if not self.warranty_purchase:
            return super()._create_picking()

        # Buscar el tipo de operación de garantía
        warranty_picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('reception_operation_type', '=', 'garantia'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if not warranty_picking_type:
            raise UserError(
                'No se encontró un tipo de operación de recepción configurado '
                'como "Garantía" para la empresa %s. '
                'Por favor, configure un tipo de operación de recepción con '
                'el tipo "Garantía" antes de proceder.' % self.company_id.name
            )

        # Temporalmente cambiar el picking_type_id para esta operación
        original_picking_type = self.picking_type_id
        self.picking_type_id = warranty_picking_type
        
        try:
            # Llamar al método padre con el tipo de operación de garantía
            result = super()._create_picking()
        finally:
            # Restaurar el tipo de operación original
            self.picking_type_id = original_picking_type

        return result

    @api.model
    def create(self, vals):
        """Asegurar que el campo warranty_purchase tenga valor por defecto"""
        if 'warranty_purchase' not in vals:
            vals['warranty_purchase'] = False
        return super().create(vals)