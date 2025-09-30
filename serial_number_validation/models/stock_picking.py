from odoo import models, fields, api
from odoo.exceptions import ValidationError

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    serial_validation_enabled = fields.Boolean(
        string='Validación de Series Habilitada',
        compute='_compute_serial_validation_enabled',
        store=False,
        groups="base.group_user"
    )
    
    @api.depends('picking_type_id', 'move_line_ids.product_id.tracking')
    def _compute_serial_validation_enabled(self):
        """Determina si la validación de series está habilitada para este picking"""
        for picking in self:
            has_serial_products = any(
                line.product_id.tracking == 'serial' 
                for line in picking.move_line_ids
            )
            picking.serial_validation_enabled = (
                has_serial_products and 
                picking.picking_type_id.code in ['incoming', 'outgoing', 'internal']
            )
    
    @api.model
    def validate_serial_realtime(self, quant_id, picking_id, product_id, move_line_id=None):
        """Validación en tiempo real para llamadas JavaScript"""
        if not quant_id or not picking_id:
            return {'valid': True}
        
        quant = self.env['stock.quant'].browse(quant_id)
        picking = self.browse(picking_id)
        product = self.env['product.product'].browse(product_id)
        
        # Solo validar productos con seguimiento por serie
        if product.tracking != 'serial':
            return {'valid': True}
        
        # Validar duplicados dentro del picking
        duplicate_result = self._check_duplicate_in_picking(
            quant_id, picking_id, move_line_id
        )
        if not duplicate_result['valid']:
            return duplicate_result
        
        # Validar disponibilidad para entregas
        if picking.picking_type_id.code == 'outgoing':
            availability_result = self._check_serial_availability(
                quant_id, picking_id, move_line_id
            )
            if not availability_result['valid']:
                return availability_result
        
        return {'valid': True}
    
    @api.model
    def _check_duplicate_in_picking(self, quant_id, picking_id, move_line_id=None):
        """Verifica duplicados dentro del mismo picking"""
        # Obtener el producto del quant
        quant = self.env['stock.quant'].browse(quant_id)
        if not quant.product_id:
            return {'valid': True}
        
        domain = [
            ('picking_id', '=', picking_id),
            ('quant_id', '=', quant_id),
            ('product_id', '=', quant.product_id.id)  # Agregar filtro por producto
        ]
        
        if move_line_id:
            domain.append(('id', '!=', move_line_id))
        
        duplicate_lines = self.env['stock.move.line'].search(domain)
        
        if duplicate_lines:
            return {
                'valid': False,
                'message': 'El número digitado ya se encuentra registrado en este conduce'
            }
        
        return {'valid': True}
    
    @api.model
    def _check_serial_availability(self, quant_id, picking_id, move_line_id=None):
        """Verifica disponibilidad del número de serie para entregas"""
        # Obtener el producto del quant
        quant = self.env['stock.quant'].browse(quant_id)
        if not quant.product_id:
            return {'valid': True}
        
        domain = [
            ('quant_id', '=', quant_id),
            ('product_id', '=', quant.product_id.id),  # Agregar filtro por producto
            ('picking_id.picking_type_id.code', '=', 'outgoing'),
            ('picking_id.state', 'in', ['waiting', 'confirmed', 'assigned']),
            ('picking_id', '!=', picking_id)
        ]
        
        if move_line_id:
            domain.append(('id', '!=', move_line_id))
        
        conflicting_lines = self.env['stock.move.line'].search(domain)
        
        if conflicting_lines:
            serial_name = quant.lot_id.name if quant.lot_id else str(quant.id)
            conflicting_picking = conflicting_lines[0].picking_id
            return {
                'valid': False,
                'message': f'El número de serie {serial_name} ya está siendo usado en el conduce {conflicting_picking.name}'
            }
        
        return {'valid': True}
    
    @api.model
    def barcode_validate_serial(self, barcode, picking_id):
        """Validación de número de serie desde scanner de código de barras"""
        picking = self.browse(picking_id)
        
        if not picking.exists():
            return {'valid': False, 'message': 'Picking no encontrado'}
        
        # Buscar o crear lote basado en el código de barras
        product_ids = picking.move_lines.mapped('product_id').filtered(
            lambda p: p.tracking == 'serial'
        )
        
        if not product_ids:
            return {'valid': False, 'message': 'No hay productos con seguimiento por serie'}
        
        # Buscar lote existente
        lot = None
        for product in product_ids:
            lot = self.env['stock.lot'].search([
                ('name', '=', barcode),
                ('product_id', '=', product.id)
            ], limit=1)
            if lot:
                break
        
        # Para operaciones de entrada, crear nuevo lote si no existe
        if not lot and picking.picking_type_id.code == 'incoming':
            # Tomar el primer producto con seguimiento por serie
            product = product_ids[0]
            lot = self.env['stock.lot'].create({
                'name': barcode,
                'product_id': product.id,
                'company_id': picking.company_id.id
            })
        
        if not lot:
            return {
                'valid': False, 
                'message': f'Número de serie {barcode} no encontrado'
            }
        
        # Validar usando lógica existente
        validation_result = self.validate_serial_realtime(
            lot.id, picking_id, lot.product_id.id
        )
        
        return {
            'lot_id': lot.id if lot else False,
            'product_id': lot.product_id.id if lot else False,
            'validation': validation_result
        }
    @api.model
    def _check_duplicate_in_picking_by_lot(self, lot_id, picking_id, move_line_id=None):
        """Verifica duplicados por lot_id"""
        domain = [
            ('picking_id', '=', picking_id),
            ('lot_id', '=', lot_id)
        ]
        
        if move_line_id:
            domain.append(('id', '!=', move_line_id))
        
        duplicate_lines = self.env['stock.move.line'].search(domain)
        
        if duplicate_lines:
            return {
                'valid': False,
                'message': 'El número digitado ya se encuentra registrado en este conduce'
            }
        
        return {'valid': True}

    @api.model
    def _check_serial_availability_by_lot(self, lot_id, picking_id, move_line_id=None):
        """Verifica disponibilidad por lot_id"""
        domain = [
            ('lot_id', '=', lot_id),
            ('picking_id.picking_type_id.code', '=', 'outgoing'),
            ('picking_id.state', 'in', ['waiting', 'confirmed', 'assigned']),
            ('picking_id', '!=', picking_id)
        ]
        
        if move_line_id:
            domain.append(('id', '!=', move_line_id))
        
        conflicting_lines = self.env['stock.move.line'].search(domain)
        
        if conflicting_lines:
            lot = self.env['stock.lot'].browse(lot_id)
            conflicting_picking = conflicting_lines[0].picking_id
            return {
                'valid': False,
                'message': f'El número de serie {lot.name} ya está siendo usado en el conduce {conflicting_picking.name}'
            }
        
        return {'valid': True}