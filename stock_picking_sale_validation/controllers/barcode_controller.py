from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError
import json
import logging

_logger = logging.getLogger(__name__)

class StockBarcodeValidationController(http.Controller):

    @http.route('/stock_barcode/validate_product', type='json', auth='user')
    def validate_product_for_picking(self, picking_id, product_id, **kwargs):
        """
        Endpoint para validar un producto específico para un picking
        """
        try:
            picking = request.env['stock.picking'].browse(picking_id)
            
            if not picking.exists():
                return {
                    'success': False,
                    'message': 'Picking no encontrado'
                }
            
            # Validar el producto
            if picking._check_picking_type_and_origin():
                picking._validate_product_in_sale_order(product_id)
            
            # Obtener información del producto
            product = request.env['product.product'].browse(product_id)
            
            return {
                'success': True,
                'product_name': product.display_name,
                'message': 'Producto válido para este picking'
            }
            
        except ValidationError as e:
            return {
                'success': False,
                'message': str(e)
            }
        except Exception as e:
            _logger.error(f"Error validating product: {e}")
            return {
                'success': False,
                'message': f'Error de validación: {str(e)}'
            }

    @http.route('/stock_barcode/get_allowed_products', type='json', auth='user')
    def get_allowed_products(self, picking_id, **kwargs):
        """
        Obtiene la lista de productos permitidos para un picking
        """
        try:
            picking = request.env['stock.picking'].browse(picking_id)
            
            if not picking.exists():
                return {
                    'success': False,
                    'message': 'Picking no encontrado'
                }
            
            if not picking._check_picking_type_and_origin():
                return {
                    'success': True,
                    'all_products_allowed': True,
                    'message': 'Todos los productos están permitidos'
                }
            
            sale_order = picking._get_sale_order_from_origin()
            if not sale_order:
                return {
                    'success': True,
                    'all_products_allowed': True,
                    'message': 'No hay restricciones de productos'
                }
            
            # Obtener productos de la orden de venta
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
            
            return {
                'success': True,
                'all_products_allowed': False,
                'products': products_data,
                'sale_order_name': sale_order.name,
                'message': 'Lista de productos obtenida correctamente'
            }
            
        except Exception as e:
            _logger.error(f"Error getting allowed products: {e}")
            return {
                'success': False,
                'message': f'Error obteniendo productos: {str(e)}'
            }

    @http.route('/stock_barcode/scan_product', type='json', auth='user')
    def scan_product_barcode(self, picking_id, barcode, **kwargs):
        """
        Procesa el escaneo de un código de barras
        """
        try:
            picking = request.env['stock.picking'].browse(picking_id)
            
            if not picking.exists():
                return {
                    'success': False,
                    'message': 'Picking no encontrado'
                }
            
            # Buscar producto por código de barras
            product = request.env['product.product'].search([
                ('barcode', '=', barcode)
            ], limit=1)
            
            if not product:
                # Intentar buscar por referencia interna
                product = request.env['product.product'].search([
                    ('default_code', '=', barcode)
                ], limit=1)
            
            if not product:
                return {
                    'success': False,
                    'message': f'Producto no encontrado para el código: {barcode}'
                }
            
            # Validar el producto antes de agregarlo
            if picking._check_picking_type_and_origin():
                try:
                    picking._validate_product_in_sale_order(product.id, product.uom_id.id)
                except ValidationError as e:
                    return {
                        'success': False,
                        'message': str(e),
                        'product_name': product.display_name
                    }
            
            return {
                'success': True,
                'product_id': product.id,
                'product_name': product.display_name,
                'product_code': product.default_code or '',
                'uom_name': product.uom_id.name,
                'message': 'Producto válido, puede ser agregado'
            }
            
        except Exception as e:
            _logger.error(f"Error scanning barcode: {e}")
            return {
                'success': False,
                'message': f'Error procesando código de barras: {str(e)}'
            }

    @http.route('/stock_barcode/get_picking_info', type='json', auth='user')
    def get_picking_info(self, picking_id, **kwargs):
        """
        Obtiene información completa del picking para la interfaz de códigos de barras
        """
        try:
            picking = request.env['stock.picking'].browse(picking_id)
            
            if not picking.exists():
                return {
                    'success': False,
                    'message': 'Picking no encontrado'
                }
            
            info = {
                'success': True,
                'picking_name': picking.name,
                'picking_type': picking.picking_type_id.name,
                'state': picking.state,
                'origin': picking.origin or '',
                'partner_name': picking.partner_id.name if picking.partner_id else '',
                'validation_active': False,
                'sale_order_name': '',
                'allowed_products_count': 0
            }
            
            # Información específica para pickings con validación
            if picking._check_picking_type_and_origin():
                sale_order = picking._get_sale_order_from_origin()
                if sale_order:
                    info.update({
                        'validation_active': True,
                        'sale_order_name': sale_order.name,
                        'allowed_products_count': len(sale_order.order_line.mapped('product_id'))
                    })
            
            return info
            
        except Exception as e:
            _logger.error(f"Error getting picking info: {e}")
            return {
                'success': False,
                'message': f'Error obteniendo información: {str(e)}'
            }