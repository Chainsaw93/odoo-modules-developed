from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Campo Condición - Obligatorio
    condicion = fields.Selection([
        ('consignacion', 'Consignación'),
        ('contrato_material', 'Contrato de material gastable'),
        ('cotizacion', 'Cotización'),
        ('espera_po', 'En espera de P.O.'),
        ('garantia', 'Garantía'),
        ('otros', 'Otros'),
        ('po', 'PO'),
        ('prestamo', 'Préstamo'),
        ('proyecto', 'Proyecto'),
        ('verbal', 'Verbal'),
    ], string='Condición', required=True, help="Condición del picking")

    # Campo Vía - Obligatorio
    via = fields.Selection([
        ('fedex', 'FedEx'),
        ('local', 'Local'),
        ('mensajeria', 'Mensajería'),
        ('metro', 'Metro'),
        ('terceros', 'Terceros'),
        ('uber', 'Uber'),
        ('vendedor', 'Vendedor'),
    ], string='Vía', required=True, help="Medio de transporte o entrega")

    # Campo Orden de compra - No editable, calculado
    orden_compra = fields.Char(
        string='Orden de compra',
        compute='_compute_orden_compra',
        store=True,
        readonly=True,
        help="Referencia de orden de compra desde la venta relacionada"
    )

    @api.depends('sale_id', 'sale_id.client_order_ref')
    def _compute_orden_compra(self):
        """Calcula el campo orden_compra basado en el sale_order_ref del sale.order relacionado"""
        for picking in self:
            if picking.sale_id and picking.sale_id.client_order_ref:
                picking.orden_compra = picking.sale_id.client_order_ref
            else:
                picking.orden_compra = False