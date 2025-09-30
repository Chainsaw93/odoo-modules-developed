from odoo import models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class StockSerialValidationService(models.AbstractModel):
    """
    Servicio central de validación de números de serie
    Proporciona validación unificada para todos los contextos de stock
    """
    _name = 'stock.serial.validation.service'
    _description = 'Stock Serial Validation Service'

    # Registry de validadores por contexto
    _context_validators = {}

    @classmethod
    def register_validator(cls, context_type, validator_method):
        """Registrar validador específico por contexto"""
        cls._context_validators[context_type] = validator_method

    @api.model
    def validate_serial_number(self, product_id, serial_number, picking_id=None, 
                              context_type='default', exclude_line_id=None):
        """
        Validación principal de números de serie
        
        :param product_id: ID del producto
        :param serial_number: Número de serie a validar
        :param picking_id: ID del picking (opcional)
        :param context_type: Tipo de contexto (form, wizard, barcode, etc.)
        :param exclude_line_id: ID de línea a excluir de la validación
        :return: Dict con resultado de validación
        """
        if not product_id or not serial_number:
            return {'valid': False, 'message': _('Producto y número de serie son requeridos')}

        # Obtener el producto
        product = self.env['product.product'].browse(product_id)
        if not product.exists() or product.tracking != 'serial':
            return {'valid': True, 'message': _('Producto no requiere validación de serie')}

        try:
            # Validación 1: Duplicados en el mismo picking
            if picking_id:
                duplicate_in_picking = self._check_duplicate_in_picking(
                    product_id, serial_number, picking_id, exclude_line_id
                )
                if not duplicate_in_picking['valid']:
                    return duplicate_in_picking

            # Validación 2: Duplicados en otros pickings (solo para entregas)
            if picking_id:
                picking = self.env['stock.picking'].browse(picking_id)
                if picking.exists() and picking.picking_type_id.code == 'outgoing':
                    duplicate_in_others = self._check_duplicate_in_other_pickings(
                        product_id, serial_number, picking_id, exclude_line_id
                    )
                    if not duplicate_in_others['valid']:
                        return duplicate_in_others

            # Validación específica por contexto
            if context_type in self._context_validators:
                context_result = self._context_validators[context_type](
                    self, product_id, serial_number, picking_id, exclude_line_id
                )
                if not context_result['valid']:
                    return context_result

            return {'valid': True, 'message': _('Número de serie válido')}

        except Exception as e:
            _logger.error(f"Error en validación de serie: {str(e)}")
            return {'valid': False, 'message': _('Error interno en validación')}

    def _check_duplicate_in_picking(self, product_id, serial_number, picking_id, exclude_line_id):
        """Verificar duplicados en el mismo picking"""
        domain = [
            ('picking_id', '=', picking_id),
            ('product_id', '=', product_id),
            '|',
            ('lot_name', '=', serial_number),
            ('lot_id.name', '=', serial_number)
        ]
        
        if exclude_line_id:
            domain.append(('id', '!=', exclude_line_id))

        duplicates = self.env['stock.move.line'].search(domain, limit=1)
        
        if duplicates:
            return {
                'valid': False,
                'message': _('El número digitado ya se encuentra registrado en este conduce'),
                'error_type': 'duplicate_in_picking'
            }
        
        return {'valid': True, 'message': ''}

    def _check_duplicate_in_other_pickings(self, product_id, serial_number, picking_id, exclude_line_id):
        """Verificar duplicados en otros pickings pendientes"""
        domain = [
            ('picking_id.picking_type_id.code', '=', 'outgoing'),
            ('picking_id.state', 'in', ['waiting', 'assigned']),
            ('picking_id', '!=', picking_id),
            ('product_id', '=', product_id),
            '|',
            ('lot_name', '=', serial_number),
            ('lot_id.name', '=', serial_number)
        ]
        
        if exclude_line_id:
            domain.append(('id', '!=', exclude_line_id))

        other_lines = self.env['stock.move.line'].search(domain, limit=1)
        
        if other_lines:
            other_picking = other_lines[0].picking_id
            return {
                'valid': False,
                'message': _('El número de serie "%s" ya está siendo utilizado en otro conduce pendiente (%s)') % (
                    serial_number, other_picking.name
                ),
                'error_type': 'duplicate_in_other_picking',
                'other_picking': other_picking.name
            }
        
        return {'valid': True, 'message': ''}

    @api.model
    def validate_serial_batch(self, validation_data):
        """
        Validación por lotes para optimizar rendimiento
        
        :param validation_data: Lista de diccionarios con datos de validación
        :return: Diccionario con resultados de validación
        """
        results = {}
        
        # Agrupar por producto para validación eficiente
        product_groups = {}
        for data in validation_data:
            product_id = data.get('product_id')
            if product_id not in product_groups:
                product_groups[product_id] = []
            product_groups[product_id].append(data)

        # Validar por grupos de producto
        for product_id, items in product_groups.items():
            product = self.env['product.product'].browse(product_id)
            
            if not product.exists() or product.tracking != 'serial':
                for item in items:
                    key = f"{item.get('product_id')}_{item.get('serial_number')}"
                    results[key] = {'valid': True, 'message': _('No requiere validación')}
                continue

            # Obtener números de serie para búsqueda única
            serial_numbers = [item.get('serial_number') for item in items if item.get('serial_number')]
            
            if serial_numbers:
                # Búsqueda única para todos los números de serie del producto
                existing_lines = self.env['stock.move.line'].search([
                    ('product_id', '=', product_id),
                    '|',
                    ('lot_name', 'in', serial_numbers),
                    ('lot_id.name', 'in', serial_numbers)
                ])
                
                existing_serials = set()
                for line in existing_lines:
                    if line.lot_name:
                        existing_serials.add(line.lot_name)
                    if line.lot_id:
                        existing_serials.add(line.lot_id.name)

                # Evaluar cada item
                for item in items:
                    serial_number = item.get('serial_number')
                    key = f"{product_id}_{serial_number}"
                    
                    if serial_number in existing_serials:
                        results[key] = {
                            'valid': False,
                            'message': _('Número de serie duplicado')
                        }
                    else:
                        results[key] = {
                            'valid': True,
                            'message': _('Válido')
                        }

        return results

    @api.model
    def is_serial_validation_enabled(self):
        """Verificar si la validación de series está habilitada"""
        return self.env['ir.config_parameter'].sudo().get_param(
            'stock_serial_validation.enabled', 'True'
        ) == 'True'

    @api.model  
    def get_validation_context_info(self, context_type='default'):
        """Obtener información de contexto para validación"""
        return {
            'enabled': self.is_serial_validation_enabled(),
            'context_type': context_type,
            'company_id': self.env.company.id,
            'user_id': self.env.user.id
        }