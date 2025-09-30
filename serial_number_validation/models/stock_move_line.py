from odoo import models, fields, api
from odoo.exceptions import ValidationError

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    
    serial_validation_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('valid', 'Válido'),
        ('invalid', 'Inválido'),
        ('duplicate', 'Duplicado')
    ], string='Estado de Validación', default='pending', store=False)
    
    @api.constrains('quant_id', 'picking_id', 'product_id')
    def _check_serial_number_constraints(self):
        """Validación completa de números de serie"""
        for line in self:
            if not line.quant_id or line.product_id.tracking != 'serial':
                continue
            
            self._validate_serial_uniqueness(line)
            self._validate_serial_availability(line)
            self._validate_operation_type_rules(line)
    
    def _validate_serial_uniqueness(self, line):
        """Validar unicidad del número de serie dentro del picking"""
        domain = [
            ('picking_id', '=', line.picking_id.id),
            ('quant_id', '=', line.quant_id.id),
            ('id', '!=', line.id)
        ]
        
        if self.search_count(domain) > 0:
            raise ValidationError(
                "El número digitado ya se encuentra registrado en este conduce"
            )
    
    def _validate_serial_availability(self, line):
        """Validar disponibilidad del número de serie para entregas"""
        if line.picking_id.picking_type_id.code != 'outgoing':
            return
        
        domain = [
            ('quant_id', '=', line.quant_id.id),
            ('picking_id.picking_type_id.code', '=', 'outgoing'),
            ('picking_id.state', 'in', ['waiting', 'confirmed', 'assigned']),
            ('picking_id', '!=', line.picking_id.id),
            ('id', '!=', line.id)
        ]
        
        conflicting_lines = self.search(domain)
        if conflicting_lines:
            quant_name = line.quant_id.lot_id.name if line.quant_id.lot_id else str(line.quant_id.id)
            conflicting_picking = conflicting_lines[0].picking_id
            raise ValidationError(
                f"El número de serie {quant_name} ya está siendo usado en el conduce {conflicting_picking.name}"
            )
    
    def _validate_operation_type_rules(self, line):
        """Validar reglas específicas por tipo de operación"""
        operation_type = line.picking_id.picking_type_id.code
        
        if operation_type == 'incoming':
            # Para recepciones, el quant puede ser nuevo o existente
            pass
        elif operation_type == 'outgoing':
            # Para entregas, verificar que el quant tenga stock disponible
            self._validate_outgoing_stock_availability(line)
        elif operation_type == 'internal':
            # Para traslados internos, solo verificar duplicados
            pass
    
    def _validate_outgoing_stock_availability(self, line):
        """Validar que hay stock disponible para entrega"""
        if line.quant_id and line.quant_id.quantity <= 0:
            quant_name = line.quant_id.lot_id.name if line.quant_id.lot_id else str(line.quant_id.id)
            raise ValidationError(
                f"El número de serie {quant_name} no tiene stock disponible"
            )
    
    @api.onchange('lot_id')
    def _onchange_lot_id_validation(self):
        """Validación en tiempo real al cambiar el lote"""
        if not self.lot_id or not self.picking_id or self.product_id.tracking != 'serial':
            return
        
        # Verificar duplicados en el picking actual
        duplicates = self.picking_id.move_line_ids.filtered(
            lambda l: l.lot_id == self.lot_id and l.id != self.id and l != self
        )
        
        if duplicates:
            return {
                'warning': {
                    'title': 'Número de serie duplicado',
                    'message': 'El número digitado ya se encuentra registrado en este conduce'
                }
            }
        
        # Verificar disponibilidad para entregas
        if self.picking_id.picking_type_id.code == 'outgoing':
            conflicting_lines = self.env['stock.move.line'].search([
                ('lot_id', '=', self.lot_id.id),
                ('picking_id.picking_type_id.code', '=', 'outgoing'),
                ('picking_id.state', 'in', ['waiting', 'confirmed', 'assigned']),
                ('picking_id', '!=', self.picking_id.id)
            ])
            
            if conflicting_lines:
                conflicting_picking = conflicting_lines[0].picking_id
                return {
                    'warning': {
                        'title': 'Número de serie no disponible',
                        'message': f'El número de serie {self.lot_id.name} ya está siendo usado en el conduce {conflicting_picking.name}'
                    }
                }
    
    @api.model
    def create(self, vals):
        """Override create para validar al crear"""
        line = super(StockMoveLine, self).create(vals)
        if line.lot_id and line.product_id.tracking == 'serial':
            line._check_serial_number_constraints()
        return line
    
    def write(self, vals):
        """Override write para validar al actualizar"""
        result = super(StockMoveLine, self).write(vals)
        if 'lot_id' in vals:
            for line in self:
                if line.lot_id and line.product_id.tracking == 'serial':
                    line._check_serial_number_constraints()
        return result
