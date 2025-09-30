from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _get_sale_order_from_origin(self):
        """Obtiene la orden de venta desde el campo origin"""
        if not self.origin:
            return False
        
        # Buscar el patrón de nombre de sale.order (ej: SO001, S00001, etc.)
        sale_order = self.env['sale.order'].search([('name', '=', self.origin)], limit=1)
        return sale_order

    def _check_picking_type_and_origin(self):
        """Verifica si es un picking de entrega con origen en venta"""
        return (self.picking_type_id.code == 'outgoing' and 
                self.origin and 
                self._get_sale_order_from_origin())

    def _validate_product_in_sale_order(self, product_id, uom_id=None):
        """Valida si un producto está en la orden de venta y su UOM"""
        if not self._check_picking_type_and_origin():
            return True
            
        sale_order = self._get_sale_order_from_origin()
        if not sale_order:
            return True
            
        # Buscar el producto en las líneas de la orden de venta
        sale_line = sale_order.order_line.filtered(
            lambda line: line.product_id.id == product_id
        )
        
        if not sale_line:
            product = self.env['product.product'].browse(product_id)
            raise ValidationError(
                _("El producto %s no está en el pedido de venta %s. No puede ser agregado al Documento.") % 
                (product.display_name, sale_order.name)
            )
        
        # Validar unidad de medida si se proporciona
        if uom_id:
            valid_uoms = sale_line.mapped('product_uom.id')
            if uom_id not in valid_uoms:
                product = self.env['product.product'].browse(product_id)
                uom = self.env['uom.uom'].browse(uom_id)
                expected_uom = sale_line[0].product_uom.name
                raise ValidationError(
                    _("El producto %s debe usar la unidad de medida '%s' según el pedido de venta %s. No se permite usar '%s'.") % 
                    (product.display_name, expected_uom, sale_order.name, uom.name)
                )
        
        return True

    def get_allowed_product_ids(self):
        """Método helper para obtener IDs de productos permitidos"""
        if not self._check_picking_type_and_origin():
            return []
        
        sale_order = self._get_sale_order_from_origin()
        if not sale_order:
            return []
        
        return sale_order.order_line.mapped('product_id.id')

    def action_show_allowed_products(self):
        """Acción para mostrar productos permitidos en una ventana emergente"""
        if not self._check_picking_type_and_origin():
            raise UserError(_("Esta función solo está disponible para entregas basadas en órdenes de venta."))
        
        sale_order = self._get_sale_order_from_origin()
        if not sale_order:
            raise UserError(_("No se encontró la orden de venta asociada."))
        
        products = sale_order.order_line.mapped('product_id')
        product_info = []
        
        for line in sale_order.order_line:
            if line.product_id:
                product_info.append(
                    f"• {line.product_id.display_name} - "
                    f"Cantidad: {line.product_uom_qty} {line.product_uom.name}"
                )
        
        message = _("Productos permitidos para el pedido de venta %s:\n\n%s") % (
            sale_order.name, 
            '\n'.join(product_info)
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Productos Permitidos'),
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """Override para inyectar contexto dinámico en las vistas"""
        result = super().get_view(view_id, view_type, **options)
        
        # Solo aplicar para vistas de formulario
        if view_type == 'form' and self.env.context.get('active_model') == 'stock.picking':
            picking_id = self.env.context.get('active_id')
            if picking_id:
                picking = self.browse(picking_id)
                if picking._check_picking_type_and_origin():
                    allowed_products = picking.get_allowed_product_ids()
                    if allowed_products:
                        # Inyectar productos permitidos en el contexto de la vista
                        if 'context' not in result:
                            result['context'] = {}
                        result['context'].update({
                            'allowed_product_ids': allowed_products,
                            'restrict_products': True
                        })
        
        return result

    def button_validate(self):
        """Override para validar antes de confirmar el picking"""
        if self._check_picking_type_and_origin():
            for move in self.move_ids:
                if move.product_id and move.quantity > 0:
                    try:
                        self._validate_product_in_sale_order(
                            move.product_id.id, 
                            move.product_uom.id
                        )
                    except ValidationError:
                        raise
        
        return super().button_validate()

class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """Override para inyectar contexto en vistas de stock.move"""
        result = super().get_view(view_id, view_type, **options)
        
        # Inyectar información de productos permitidos si viene del contexto de picking
        picking_id = self.env.context.get('picking_id') or self.env.context.get('default_picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            if picking._check_picking_type_and_origin():
                allowed_products = picking.get_allowed_product_ids()
                if allowed_products:
                    if 'context' not in result:
                        result['context'] = {}
                    result['context'].update({
                        'allowed_product_ids': allowed_products,
                        'restrict_products': True
                    })
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Override create para validar productos al crear movimientos"""
        for vals in vals_list:
            if 'picking_id' in vals and vals['picking_id']:
                picking = self.env['stock.picking'].browse(vals['picking_id'])
                if vals.get('product_id') and picking._check_picking_type_and_origin():
                    picking._validate_product_in_sale_order(
                        vals['product_id'], 
                        vals.get('product_uom')
                    )
        return super().create(vals_list)

    def write(self, vals):
        """Override write para validar cambios en productos existentes"""
        if vals.get('product_id') or vals.get('product_uom'):
            for move in self:
                if move.picking_id and move.picking_id._check_picking_type_and_origin():
                    product_id = vals.get('product_id', move.product_id.id)
                    uom_id = vals.get('product_uom', move.product_uom.id)
                    move.picking_id._validate_product_in_sale_order(product_id, uom_id)
        return super().write(vals)

    @api.onchange('product_id')
    def _onchange_product_id_domain(self):
        """Filtrar productos disponibles basado en la orden de venta"""
        result = {'domain': {'product_id': []}}
        
        if self.picking_id and self.picking_id._check_picking_type_and_origin():
            allowed_products = self.picking_id.get_allowed_product_ids()
            if allowed_products:
                result['domain']['product_id'] = [('id', 'in', allowed_products)]
                
        return result

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """Override para inyectar contexto en vistas de stock.move.line"""
        result = super().get_view(view_id, view_type, **options)
        
        # Inyectar información de productos permitidos
        picking_id = self.env.context.get('picking_id') or self.env.context.get('default_picking_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            if picking._check_picking_type_and_origin():
                allowed_products = picking.get_allowed_product_ids()
                if allowed_products:
                    if 'context' not in result:
                        result['context'] = {}
                    result['context'].update({
                        'allowed_product_ids': allowed_products,
                        'restrict_products': True
                    })
        
        return result

    @api.model_create_multi  
    def create(self, vals_list):
        """Override create para validar en move lines (usado en códigos de barras)"""
        for vals in vals_list:
            picking = None
            if 'picking_id' in vals and vals['picking_id']:
                picking = self.env['stock.picking'].browse(vals['picking_id'])
            elif 'move_id' in vals and vals['move_id']:
                move = self.env['stock.move'].browse(vals['move_id'])
                picking = move.picking_id
                
            if picking and vals.get('product_id') and picking._check_picking_type_and_origin():
                picking._validate_product_in_sale_order(
                    vals['product_id'],
                    vals.get('product_uom_id')
                )
        return super().create(vals_list)

    def write(self, vals):
        """Override write para validar cambios en move lines"""
        if vals.get('product_id') or vals.get('product_uom_id'):
            for move_line in self:
                picking = move_line.picking_id or (move_line.move_id and move_line.move_id.picking_id)
                if picking and picking._check_picking_type_and_origin():
                    product_id = vals.get('product_id', move_line.product_id.id)
                    uom_id = vals.get('product_uom_id', move_line.product_uom_id.id)
                    picking._validate_product_in_sale_order(product_id, uom_id)
        return super().write(vals)

    @api.onchange('product_id')
    def _onchange_product_id_domain(self):
        """Filtrar productos disponibles en move lines"""
        result = {'domain': {'product_id': []}}
        
        picking = self.picking_id or (self.move_id and self.move_id.picking_id)
        if picking and picking._check_picking_type_and_origin():
            allowed_products = picking.get_allowed_product_ids()
            if allowed_products:
                result['domain']['product_id'] = [('id', 'in', allowed_products)]
        
        return result

class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=100, name_get_uid=None):
        """Override para filtrar productos según el contexto del picking"""
        if domain is None:
            domain = []
        
        # Aplicar filtro si viene del contexto de un picking y está restringido
        if self.env.context.get('restrict_products') and self.env.context.get('allowed_product_ids'):
            allowed_products = self.env.context.get('allowed_product_ids', [])
            domain = domain + [('id', 'in', allowed_products)]
        
        return super()._name_search(name, domain, operator, limit, name_get_uid)

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Override search_read para aplicar filtros de picking"""
        if domain is None:
            domain = []
        
        # Aplicar filtro si está restringido por picking
        if self.env.context.get('restrict_products') and self.env.context.get('allowed_product_ids'):
            allowed_products = self.env.context.get('allowed_product_ids', [])
            domain = domain + [('id', 'in', allowed_products)]
        
        return super().search_read(domain, fields, offset, limit, order)

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Override name_search para aplicar filtros de picking"""
        if args is None:
            args = []
        
        # Aplicar filtro si está restringido por picking
        if self.env.context.get('restrict_products') and self.env.context.get('allowed_product_ids'):
            allowed_products = self.env.context.get('allowed_product_ids', [])
            args = args + [('id', 'in', allowed_products)]
        
        return super().name_search(name, args, operator, limit)

# Extensión específica para la interfaz de códigos de barras
class StockPickingBarcodeInterface(models.Model):
    _inherit = 'stock.picking'

    def _add_product(self, product, qty=1.0, uom=None, **kwargs):
        """Override para validar productos agregados vía códigos de barras"""
        # Validar antes de agregar el producto
        if product and self._check_picking_type_and_origin():
            uom_id = uom.id if uom else product.uom_id.id
            self._validate_product_in_sale_order(product.id, uom_id)
        
        return super()._add_product(product, qty, uom, **kwargs)

    @api.model
    def get_barcode_view_state(self):
        """Obtener estado con información de productos permitidos"""
        result = super().get_barcode_view_state()
        
        # Agregar información sobre productos permitidos
        if self._check_picking_type_and_origin():
            sale_order = self._get_sale_order_from_origin()
            if sale_order:
                result['sale_order_name'] = sale_order.name
                result['allowed_products'] = sale_order.order_line.mapped('product_id.id')
                result['validation_active'] = True
        
        return result

    def get_products_from_sale_order(self):
        """Método para obtener productos disponibles desde la orden de venta"""
        if not self._check_picking_type_and_origin():
            return []
            
        sale_order = self._get_sale_order_from_origin()
        if not sale_order:
            return []
            
        products_data = []
        for line in sale_order.order_line:
            if line.product_id:
                products_data.append({
                    'id': line.product_id.id,
                    'name': line.product_id.display_name,
                    'default_code': line.product_id.default_code or '',
                    'barcode': line.product_id.barcode or '',
                    'uom_id': line.product_uom.id,
                    'uom_name': line.product_uom.name,
                    'qty_ordered': line.product_uom_qty,
                    'qty_delivered': line.qty_delivered,
                    'qty_remaining': line.product_uom_qty - line.qty_delivered
                })
        
        return products_data