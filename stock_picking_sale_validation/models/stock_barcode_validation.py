# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import ValidationError
import logging
import json

_logger = logging.getLogger(__name__)

class StockPickingBarcodeValidation(models.Model):
    _inherit = 'stock.picking'

    def _add_product(self, product, qty=1.0, uom=None, **kwargs):
        """
        Override del método _add_product para validar productos agregados vía códigos de barras
        Este método se ejecuta cuando se escanea un código de barras en la app
        """
        # Validar antes de agregar el producto
        if product and self._check_picking_type_and_origin():
            uom_id = uom.id if uom else (product.uom_id.id if product.uom_id else False)
            
            try:
                self._validate_product_in_sale_order(product.id, uom_id)
            except ValidationError as e:
                _logger.error(f"Barcode validation error in _add_product: {e}")
                raise
        
        # Si la validación pasa, continuar con el comportamiento normal
        return super()._add_product(product, qty, uom, **kwargs)

    @api.model
    def process_barcode_from_ui(self, barcode_data):
        """
        Procesar códigos de barras desde la interfaz de usuario
        Este método maneja los datos que vienen de la interfaz web/móvil
        """
        try:
            # Ejecutar el procesamiento normal primero
            result = super().process_barcode_from_ui(barcode_data)
            
            # Realizar validaciones adicionales si es necesario
            if isinstance(barcode_data, dict) and 'picking_id' in barcode_data:
                picking_id = barcode_data.get('picking_id')
                if picking_id:
                    picking = self.browse(picking_id)
                    if hasattr(picking, '_validate_barcode_data'):
                        picking._validate_barcode_data(barcode_data)
            
            return result
            
        except ValidationError:
            # Re-lanzar ValidationError tal como está
            raise
        except Exception as e:
            # Convertir otras excepciones a ValidationError para mejor manejo en la UI
            _logger.error(f"Error processing barcode: {e}")
            raise ValidationError(_("Error procesando código de barras: %s") % str(e))

    def _validate_barcode_data(self, barcode_data):
        """
        Validación específica para datos de códigos de barras
        """
        if not isinstance(barcode_data, dict):
            return
            
        product_id = barcode_data.get('product_id')
        uom_id = barcode_data.get('uom_id') or barcode_data.get('product_uom_id')
        
        if product_id and self._check_picking_type_and_origin():
            self._validate_product_in_sale_order(product_id, uom_id)

    def action_put_in_pack(self):
        """
        Override para validar antes de empacar
        """
        # Validar que todos los productos en las líneas estén en la orden de venta
        if self._check_picking_type_and_origin():
            for move_line in self.move_line_ids:
                if move_line.product_id and move_line.quantity > 0:
                    try:
                        self._validate_product_in_sale_order(
                            move_line.product_id.id, 
                            move_line.product_uom_id.id
                        )
                    except ValidationError:
                        # Si hay un error, no permitir empacar
                        raise
        
        return super().action_put_in_pack()

    def button_validate(self):
        """
        Override para validar antes de confirmar el picking
        """
        # Validación final antes de confirmar
        if self._check_picking_type_and_origin():
            # CORREGIDO: usar move_ids en lugar de move_lines
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

    @api.model
    def get_barcode_view_state(self):
        """
        Obtener el estado de la vista de códigos de barras
        Incluye información adicional sobre validaciones
        """
        result = super().get_barcode_view_state()
        
        # Agregar información sobre validaciones activas
        if hasattr(self, '_check_picking_type_and_origin'):
            result['validation_active'] = self._check_picking_type_and_origin()
            if result['validation_active']:
                sale_order = self._get_sale_order_from_origin()
                if sale_order:
                    result['sale_order_name'] = sale_order.name
                    result['allowed_products'] = sale_order.order_line.mapped('product_id.id')
        
        return result

class StockBarcodeValidationMixin(models.AbstractModel):
    """
    Mixin para agregar validaciones de códigos de barras a otros modelos
    """
    _name = 'stock.barcode.validation.mixin'
    _description = 'Mixin para validaciones de códigos de barras'

    def _validate_scanned_product(self, product_id, picking_id=None, uom_id=None):
        """
        Método helper para validar productos escaneados
        """
        if not picking_id:
            return True
            
        picking = self.env['stock.picking'].browse(picking_id)
        if picking and picking._check_picking_type_and_origin():
            return picking._validate_product_in_sale_order(product_id, uom_id)
        
        return True

# Extensión para manejar respuestas AJAX/RPC específicas
class StockPickingBarcodeRPC(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def scan_product_barcode(self, picking_id, barcode, **kwargs):
        """
        Método RPC para escanear códigos de barras de productos
        """
        try:
            picking = self.browse(picking_id)
            
            # Buscar el producto por código de barras
            product = self.env['product.product'].search([
                ('barcode', '=', barcode)
            ], limit=1)
            
            if not product:
                # Intentar buscar por referencia interna
                product = self.env['product.product'].search([
                    ('default_code', '=', barcode)
                ], limit=1)
            
            if not product:
                return {
                    'success': False,
                    'message': _('Producto no encontrado para el código: %s') % barcode
                }
            
            # Validar el producto antes de agregarlo
            if picking._check_picking_type_and_origin():
                try:
                    picking._validate_product_in_sale_order(product.id, product.uom_id.id)
                except ValidationError as e:
                    return {
                        'success': False,
                        'message': str(e)
                    }
            
            # Si todo está bien, agregar el producto
            result = picking._add_product(product, kwargs.get('qty', 1.0))
            
            return {
                'success': True,
                'product_id': product.id,
                'product_name': product.display_name,
                'message': _('Producto agregado exitosamente')
            }
            
        except Exception as e:
            _logger.error(f"Error in scan_product_barcode: {e}")
            return {
                'success': False,
                'message': _('Error al procesar código de barras: %s') % str(e)
            }

    @api.model
    def validate_product_for_picking(self, picking_id, product_id, uom_id=None):
        """
        Método RPC para validar un producto específico para un picking
        Útil para validaciones en tiempo real desde la interfaz
        """
        try:
            picking = self.browse(picking_id)
            if picking._check_picking_type_and_origin():
                picking._validate_product_in_sale_order(product_id, uom_id)
            
            return {
                'success': True,
                'message': _('Producto válido para este picking')
            }
        except ValidationError as e:
            return {
                'success': False,
                'message': str(e)
            }
        except Exception as e:
            _logger.error(f"Error in validate_product_for_picking: {e}")
            return {
                'success': False,
                'message': _('Error en validación: %s') % str(e)
            }

    @api.model
    def get_allowed_products_for_picking(self, picking_id):
        """
        Obtiene la lista de productos permitidos para un picking específico
        """
        try:
            picking = self.browse(picking_id)
            if not picking._check_picking_type_and_origin():
                return {
                    'success': True,
                    'all_products_allowed': True,
                    'message': _('Todos los productos están permitidos')
                }
            
            sale_order = picking._get_sale_order_from_origin()
            if not sale_order:
                return {
                    'success': True,
                    'all_products_allowed': True,
                    'message': _('No hay restricciones de productos')
                }
            
            # Obtener productos y sus UOM de la orden de venta
            allowed_products = []
            for line in sale_order.order_line:
                if line.product_id:
                    allowed_products.append({
                        'product_id': line.product_id.id,
                        'product_name': line.product_id.display_name,
                        'product_code': line.product_id.default_code or '',
                        'uom_id': line.product_uom.id,
                        'uom_name': line.product_uom.name,
                        'qty_ordered': line.product_uom_qty,
                        'qty_delivered': line.qty_delivered
                    })
            
            return {
                'success': True,
                'all_products_allowed': False,
                'allowed_products': allowed_products,
                'sale_order_name': sale_order.name,
                'message': _('Lista de productos permitidos obtenida')
            }
            
        except Exception as e:
            _logger.error(f"Error in get_allowed_products_for_picking: {e}")
            return {
                'success': False,
                'message': _('Error obteniendo productos permitidos: %s') % str(e)
            }