from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _get_allowed_product_ids(self):
        """Obtiene los IDs de productos permitidos basados en la orden de venta"""
        if not self.origin or self.picking_type_code != 'outgoing':
            return []
        
        # Buscar la orden de venta por el origen
        sale_order = self.env['sale.order'].search([('name', '=', self.origin)], limit=1)
        if not sale_order:
            return []
        
        # Obtener todos los productos de las líneas de la orden de venta
        product_ids = sale_order.order_line.mapped('product_id').ids
        return product_ids

    def write(self, vals):
        """Validar que solo se agreguen productos de la orden de venta"""
        result = super().write(vals)
        
        for picking in self:
            if picking.picking_type_code == 'outgoing' and picking.origin:
                allowed_product_ids = picking._get_allowed_product_ids()
                if allowed_product_ids:
                    # Validar movimientos
                    invalid_moves = picking.move_ids_without_package.filtered(
                        lambda m: m.product_id.id not in allowed_product_ids
                    )
                    if invalid_moves:
                        product_names = ', '.join(invalid_moves.mapped('product_id.name'))
                        raise ValidationError(
                            f"Los siguientes productos no están en la orden de venta {picking.origin}: {product_names}"
                        )
        
        return result

    def action_show_allowed_products(self):
        """Acción para mostrar los productos permitidos"""
        allowed_product_ids = self._get_allowed_product_ids()
        
        if not allowed_product_ids:
            raise UserError("No se encontraron productos para esta orden de venta.")
        
        return {
            'name': f'Productos Permitidos - {self.origin}',
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', allowed_product_ids)],
            'context': {
                'create': False,
                'edit': False,
                'delete': False,
            }
        }


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, order=None):
        """Filtrar productos en búsquedas de nombre"""
        if args is None:
            args = []
        
        # Obtener el picking_id del contexto
        picking_id = self.env.context.get('picking_id') or self.env.context.get('default_picking_id')
        
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            if picking.picking_type_code == 'outgoing' and picking.origin:
                allowed_product_ids = picking._get_allowed_product_ids()
                if allowed_product_ids:
                    # Agregar filtro por producto
                    args = args + [('product_id', 'in', allowed_product_ids)]
        
        return super()._name_search(name=name, args=args, operator=operator, limit=limit, order=order)

    @api.onchange('product_id')
    def _onchange_product_id_restrict(self):
        """Validar producto seleccionado en onchange"""
        if self.product_id and self.picking_id:
            if self.picking_id.picking_type_code == 'outgoing' and self.picking_id.origin:
                allowed_product_ids = self.picking_id._get_allowed_product_ids()
                if allowed_product_ids and self.product_id.id not in allowed_product_ids:
                    self.product_id = False
                    return {
                        'warning': {
                            'title': 'Producto No Permitido',
                            'message': f'Este producto no está en la orden de venta {self.picking_id.origin}.'
                        }
                    }

    @api.model_create_multi
    def create(self, vals_list):
        """Validar en creación"""
        moves = super().create(vals_list)
        
        for move in moves:
            if move.picking_id and move.picking_id.picking_type_code == 'outgoing' and move.picking_id.origin:
                allowed_product_ids = move.picking_id._get_allowed_product_ids()
                if allowed_product_ids and move.product_id.id not in allowed_product_ids:
                    raise ValidationError(
                        f'El producto "{move.product_id.name}" no está permitido para la orden de venta {move.picking_id.origin}.'
                    )
        
        return moves


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.onchange('product_id')
    def _onchange_product_id_restrict(self):
        """Validar producto seleccionado en onchange"""
        if self.product_id and self.picking_id:
            if self.picking_id.picking_type_code == 'outgoing' and self.picking_id.origin:
                allowed_product_ids = self.picking_id._get_allowed_product_ids()
                if allowed_product_ids and self.product_id.id not in allowed_product_ids:
                    self.product_id = False
                    return {
                        'warning': {
                            'title': 'Producto No Permitido',
                            'message': f'Este producto no está en la orden de venta {self.picking_id.origin}.'
                        }
                    }

    @api.model_create_multi
    def create(self, vals_list):
        """Validar en creación"""
        move_lines = super().create(vals_list)
        
        for move_line in move_lines:
            if move_line.picking_id and move_line.picking_id.picking_type_code == 'outgoing' and move_line.picking_id.origin:
                allowed_product_ids = move_line.picking_id._get_allowed_product_ids()
                if allowed_product_ids and move_line.product_id.id not in allowed_product_ids:
                    raise ValidationError(
                        f'El producto "{move_line.product_id.name}" no está permitido para la orden de venta {move_line.picking_id.origin}.'
                    )
        
        return move_lines


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, order=None):
        """Filtrar productos basado en el contexto del picking"""
        if args is None:
            args = []
        
        # Verificar si estamos en el contexto de un picking de salida
        picking_id = self.env.context.get('picking_id') or self.env.context.get('default_picking_id')
        picking_type_code = self.env.context.get('picking_type_code')
        picking_origin = self.env.context.get('picking_origin')
        
        if picking_id and picking_type_code == 'outgoing' and picking_origin:
            picking = self.env['stock.picking'].browse(picking_id)
            allowed_product_ids = picking._get_allowed_product_ids()
            
            if allowed_product_ids:
                # Filtrar solo los productos permitidos
                args = args + [('id', 'in', allowed_product_ids)]
        
        return super()._name_search(name=name, args=args, operator=operator, limit=limit, order=order)

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Filtrar productos en búsquedas read"""
        if domain is None:
            domain = []
        
        # Verificar si estamos en el contexto de un picking de salida
        picking_id = self.env.context.get('picking_id') or self.env.context.get('default_picking_id')
        picking_type_code = self.env.context.get('picking_type_code')
        picking_origin = self.env.context.get('picking_origin')
        
        if picking_id and picking_type_code == 'outgoing' and picking_origin:
            picking = self.env['stock.picking'].browse(picking_id)
            allowed_product_ids = picking._get_allowed_product_ids()
            
            if allowed_product_ids:
                # Agregar filtro al dominio
                domain = domain + [('id', 'in', allowed_product_ids)]
        
        return super().search_read(domain=domain, fields=fields, offset=offset, limit=limit, order=order)