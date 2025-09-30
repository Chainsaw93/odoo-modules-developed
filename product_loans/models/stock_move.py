# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    # ==========================================
    # CAMPOS ESPECÍFICOS DE PRÉSTAMOS
    # ==========================================
    
    loan_return_qty = fields.Float(
        string='Cantidad de Devolución de Préstamo',
        digits='Product Unit of Measure',
        help="Cantidad específica que se devuelve de un préstamo original"
    )
    
    is_loan_move = fields.Boolean(
        string='Es Movimiento de Préstamo',
        compute='_compute_loan_move_type',
        store=True,
        help="Indica si este movimiento está relacionado con préstamos"
    )
    
    is_loan_return_move = fields.Boolean(
        string='Es Devolución de Préstamo',
        compute='_compute_loan_move_type',
        store=True,
        help="Indica si este movimiento es una devolución de préstamo"
    )
    
    original_loan_picking_id = fields.Many2one(
        'stock.picking',
        string='Préstamo Original',
        compute='_compute_original_loan_picking',
        store=True,
        help="Préstamo original si este movimiento es parte de una devolución"
    )
    
    loan_tracking_detail_ids = fields.One2many(
        'loan.tracking.detail',
        compute='_compute_loan_tracking_details',
        string='Detalles de Seguimiento Relacionados',
        help="Detalles de seguimiento de préstamos relacionados con este movimiento"
    )
    
    # Campos calculados para reporting
    related_loan_value = fields.Float(
        string='Valor del Préstamo Relacionado',
        compute='_compute_loan_financial_info',
        digits='Product Price',
        help="Valor financiero del préstamo relacionado"
    )
    
    loan_days_elapsed = fields.Integer(
        string='Días de Préstamo',
        compute='_compute_loan_financial_info',
        help="Días transcurridos desde el préstamo original"
    )
    
    # ==========================================
    # MÉTODOS COMPUTE 
    # ==========================================
    
    @api.depends('picking_id.is_loan', 'picking_id.loan_return_origin_id')
    def _compute_loan_move_type(self):
        """Determinar el tipo de movimiento relacionado con préstamos"""
        for move in self:
            if move.picking_id:
                move.is_loan_move = move.picking_id.is_loan
                move.is_loan_return_move = bool(move.picking_id.loan_return_origin_id)
            else:
                move.is_loan_move = False
                move.is_loan_return_move = False
    
    @api.depends('picking_id.loan_return_origin_id')
    def _compute_original_loan_picking(self):
        """Obtener referencia al préstamo original"""
        for move in self:
            if move.picking_id and move.picking_id.loan_return_origin_id:
                move.original_loan_picking_id = move.picking_id.loan_return_origin_id
            else:
                move.original_loan_picking_id = False
    
    def _compute_loan_tracking_details(self):
        """Obtener detalles de seguimiento relacionados"""
        for move in self:
            tracking_details = self.env['loan.tracking.detail']
            
            if move.is_loan_move:
                # Para movimientos de préstamo, buscar detalles del mismo picking
                tracking_details = self.env['loan.tracking.detail'].search([
                    ('picking_id', '=', move.picking_id.id),
                    ('product_id', '=', move.product_id.id)
                ])
            elif move.is_loan_return_move and move.original_loan_picking_id:
                # Para devoluciones, buscar detalles del préstamo original
                tracking_details = self.env['loan.tracking.detail'].search([
                    ('picking_id', '=', move.original_loan_picking_id.id),
                    ('product_id', '=', move.product_id.id)
                ])
            
            move.loan_tracking_detail_ids = tracking_details
    
    @api.depends('loan_tracking_detail_ids', 'original_loan_picking_id')
    def _compute_loan_financial_info(self):
        """Calcular información financiera del préstamo"""
        for move in self:
            total_value = 0.0
            days_elapsed = 0
            
            if move.loan_tracking_detail_ids:
                # Sumar valores de los detalles de seguimiento
                for detail in move.loan_tracking_detail_ids:
                    total_value += detail.original_cost * detail.quantity
                    if detail.loan_date:
                        delta = fields.Datetime.now() - detail.loan_date
                        days_elapsed = max(days_elapsed, delta.days)
            
            move.related_loan_value = total_value
            move.loan_days_elapsed = days_elapsed
    
    # ==========================================
    # VALIDACIONES Y CONSTRAINS
    # ==========================================
    
    @api.constrains('loan_return_qty', 'product_uom_qty')
    def _check_loan_return_qty_consistency(self):
        """Validar consistencia en cantidades de devolución"""
        for move in self:
            if move.loan_return_qty and not move.is_loan_return_move:
                raise ValidationError(_(
                    f"El campo 'Cantidad de Devolución de Préstamo' solo debe usarse "
                    f"en movimientos de devolución. Movimiento: {move.name}"
                ))
            
            if move.loan_return_qty and move.loan_return_qty > move.product_uom_qty:
                raise ValidationError(_(
                    f"La cantidad de devolución de préstamo ({move.loan_return_qty}) "
                    f"no puede ser mayor a la cantidad del movimiento ({move.product_uom_qty}). "
                    f"Producto: {move.product_id.name}"
                ))
    
    @api.constrains('product_id')
    def _check_loan_product_consistency(self):
        """Validar que el producto sea consistente con las operaciones de préstamo"""
        for move in self:
            if move.is_loan_move and not move.product_id.allow_loans:
                raise ValidationError(_(
                    f"El producto '{move.product_id.name}' no está habilitado para préstamos. "
                    f"Movimiento: {move.name}"
                ))
    
    # ==========================================
    # MÉTODOS CORE - INTEGRACIÓN CON PRÉSTAMOS
    # ==========================================
    
    def _create_loan_tracking_on_validate(self):
        """Crear registros de seguimiento cuando se valida un movimiento de préstamo"""
        self.ensure_one()
        
        if not self.is_loan_move or self.state != 'done':
            return
        
        tracking_vals = []
        
        if self.product_id.tracking == 'serial':
            # Para productos con número de serie, crear un registro por cada serie
            for move_line in self.move_line_ids:
                if move_line.lot_id and move_line.qty_done > 0:
                    tracking_vals.append({
                        'picking_id': self.picking_id.id,
                        'product_id': self.product_id.id,
                        'lot_id': move_line.lot_id.id,
                        'quantity': 1,
                        'status': 'active',
                        'loan_date': self.date or fields.Datetime.now(),
                        'original_cost': self.product_id.standard_price,
                    })
        else:
            # Para productos sin número de serie o con lote
            qty_done = sum(self.move_line_ids.mapped('qty_done'))
            if qty_done > 0:
                tracking_vals.append({
                    'picking_id': self.picking_id.id,
                    'product_id': self.product_id.id,
                    'quantity': qty_done,
                    'status': 'active',
                    'loan_date': self.date or fields.Datetime.now(),
                    'original_cost': self.product_id.standard_price,
                })
        
        if tracking_vals:
            self.env['loan.tracking.detail'].create(tracking_vals)
            _logger.info(f"Creados {len(tracking_vals)} registros de tracking para movimiento {self.name}")
    
    def _update_loan_tracking_on_return(self):
        """Actualizar tracking cuando se procesa una devolución"""
        self.ensure_one()
        
        if not (self.is_loan_return_move and self.original_loan_picking_id and self.state == 'done'):
            return
        
        qty_returned = self.loan_return_qty or sum(self.move_line_ids.mapped('qty_done'))
        
        if qty_returned <= 0:
            return
        
        # Buscar registros de tracking activos del préstamo original
        if self.product_id.tracking == 'serial':
            # Para productos con serie, marcar cada serie específica
            for move_line in self.move_line_ids:
                if move_line.lot_id and move_line.qty_done > 0:
                    tracking_records = self.env['loan.tracking.detail'].search([
                        ('picking_id', '=', self.original_loan_picking_id.id),
                        ('product_id', '=', self.product_id.id),
                        ('lot_id', '=', move_line.lot_id.id),
                        ('status', '=', 'active')
                    ])
                    
                    for record in tracking_records:
                        record.action_mark_as_returned(
                            return_picking=self.picking_id,
                            condition='good',
                            notes=f"Devuelto automáticamente via movimiento {self.name}"
                        )
        else:
            # Para productos sin serie/lote, procesar cantidad
            active_tracking = self.env['loan.tracking.detail'].search([
                ('picking_id', '=', self.original_loan_picking_id.id),
                ('product_id', '=', self.product_id.id),
                ('status', '=', 'active')
            ], order='loan_date desc')  # Devolver los más recientes primero
            
            remaining_qty = qty_returned
            
            for record in active_tracking:
                if remaining_qty <= 0:
                    break
                
                if record.quantity <= remaining_qty:
                    # Devolver este registro completo
                    record.action_mark_as_returned(
                        return_picking=self.picking_id,
                        condition='good',
                        notes=f"Devuelto automáticamente via movimiento {self.name}"
                    )
                    remaining_qty -= record.quantity
                else:
                    # Devolución parcial - dividir el registro
                    returned_record = record.copy({
                        'quantity': remaining_qty,
                        'status': 'returned_good',
                        'return_picking_id': self.picking_id.id,
                        'resolution_date': fields.Datetime.now(),
                        'return_condition_notes': f"Devolución parcial via movimiento {self.name}"
                    })
                    
                    # Actualizar cantidad restante en el registro original
                    record.quantity = record.quantity - remaining_qty
                    remaining_qty = 0
        
        _logger.info(f"Actualizado tracking de devolución para movimiento {self.name}")
    
    def _get_available_return_qty(self):
        """Obtener cantidad disponible para devolver de este producto específico"""
        self.ensure_one()
        
        if not self.original_loan_picking_id:
            return 0.0
        
        # Buscar cantidad originalmente prestada
        original_moves = self.original_loan_picking_id.move_ids_without_package.filtered(
            lambda m: m.product_id == self.product_id
        )
        
        original_qty = sum(original_moves.mapped(lambda m: sum(m.move_line_ids.mapped('qty_done'))))
        
        # Buscar cantidad ya devuelta
        returned_moves = self.env['stock.move'].search([
            ('picking_id.loan_return_origin_id', '=', self.original_loan_picking_id.id),
            ('product_id', '=', self.product_id.id),
            ('state', '=', 'done')
        ])
        
        returned_qty = sum(returned_moves.mapped(lambda m: sum(m.move_line_ids.mapped('qty_done'))))
        
        return max(0, original_qty - returned_qty)
    
    # ==========================================
    # MÉTODOS DE INTEGRACIÓN CONTABLE (de loan_accounting.py)
    # ==========================================
    
    def _create_account_move_line(self, credit_account_id, debit_account_id, journal_id, qty, description, svl_id, cost):
        """Override para manejar valoración específica de préstamos convertidos a venta"""
        
        # Si es una conversión de préstamo a venta, usar costo original
        if (self.picking_id.loan_conversion_sale_order_id and 
            hasattr(self.picking_id, 'is_loan') and 
            self.picking_id.is_loan):
            
            # Buscar el costo original del préstamo
            original_cost = self._get_original_loan_cost()
            if original_cost:
                cost = original_cost
                description = f"{description} (Conversión préstamo - Costo original: {original_cost})"
        
        # Llamada estándar con costo ajustado
        return super()._create_account_move_line(
            credit_account_id, debit_account_id, journal_id, 
            qty, description, svl_id, cost
        )
    
    def _get_original_loan_cost(self):
        """Obtener el costo original del producto al momento del préstamo"""
        # Buscar en el tracker de valoración
        valuation_tracker = self.env['loan.valuation.tracker'].search([
            ('picking_id', '=', self.picking_id.id),
            ('product_id', '=', self.product_id.id)
        ], limit=1)
        
        if valuation_tracker:
            return valuation_tracker.original_cost
        
        # Fallback: buscar en detalles de seguimiento
        tracking_detail = self.env['loan.tracking.detail'].search([
            ('picking_id', '=', self.picking_id.id),
            ('product_id', '=', self.product_id.id)
        ], limit=1)
        
        return tracking_detail.original_cost if tracking_detail else None
        
    # ==========================================
    # MÉTODOS DE OVERRIDE PARA INTEGRACIÓN
    # ==========================================
    
    def _action_done(self, cancel_backorder=False):
        """Override para manejar tracking automático al validar movimientos"""
        result = super()._action_done(cancel_backorder=cancel_backorder)
        
        for move in self:
            try:
                if move.is_loan_move:
                    # Crear tracking para préstamos
                    move._create_loan_tracking_on_validate()
                elif move.is_loan_return_move:
                    # Actualizar tracking para devoluciones
                    move._update_loan_tracking_on_return()
            except Exception as e:
                _logger.error(f"Error en tracking automático para movimiento {move.name}: {str(e)}")
                # No interrumpir el flujo principal, solo registrar error
        
        return result
    
    def write(self, vals):
        """Override para validaciones adicionales en escritura"""
        # Validar cambios en loan_return_qty
        if 'loan_return_qty' in vals:
            for move in self:
                if vals['loan_return_qty'] > 0 and not move.is_loan_return_move:
                    # Auto-marcar como movimiento de devolución si se asigna cantidad
                    if move.picking_id and not move.picking_id.loan_return_origin_id:
                        raise UserError(_(
                            f"No se puede asignar cantidad de devolución de préstamo "
                            f"a un movimiento que no es devolución. Movimiento: {move.name}"
                        ))
        
        return super().write(vals)
    
    # ==========================================
    # MÉTODOS AUXILIARES Y REPORTING
    # ==========================================
    
    def action_view_loan_tracking(self):
        """Ver detalles de seguimiento relacionados"""
        self.ensure_one()
        
        if not self.loan_tracking_detail_ids:
            raise UserError(_("Este movimiento no tiene detalles de seguimiento relacionados."))
        
        return {
            'name': f'Seguimiento de Préstamo - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'loan.tracking.detail',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.loan_tracking_detail_ids.ids)],
            'context': {'create': False}
        }
    
    def action_view_original_loan(self):
        """Ver préstamo original si es devolución"""
        self.ensure_one()
        
        if not self.original_loan_picking_id:
            raise UserError(_("Este movimiento no está asociado a un préstamo original."))
        
        return {
            'name': f'Préstamo Original - {self.original_loan_picking_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.original_loan_picking_id.id,
            'view_mode': 'form',
            'target': 'current'
        }
    
    @api.model
    def get_loan_moves_analytics(self, date_from=None, date_to=None):
        """Obtener analíticas de movimientos de préstamos"""
        domain = [('is_loan_move', '=', True)]
        
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        
        moves = self.search(domain)
        
        analytics = {
            'total_loan_moves': len(moves),
            'total_loan_value': sum(moves.mapped(lambda m: m.product_id.standard_price * m.quantity_done)),
            'products_in_loans': len(moves.mapped('product_id')),
            'partners_with_loans': len(moves.mapped('picking_id.loaned_to_partner_id')),
            'avg_loan_value': 0,
        }
        
        if analytics['total_loan_moves'] > 0:
            analytics['avg_loan_value'] = analytics['total_loan_value'] / analytics['total_loan_moves']
        
        return analytics
    
    def _get_loan_move_description(self):
        """Generar descripción legible para movimiento de préstamo"""
        self.ensure_one()
        
        if self.is_loan_move:
            return f"Préstamo: {self.product_id.name} → {self.picking_id.loaned_to_partner_id.name}"
        elif self.is_loan_return_move:
            return f"Devolución: {self.product_id.name} ← {self.picking_id.loaned_to_partner_id.name}"
        else:
            return f"Movimiento estándar: {self.product_id.name}"
    
    # ==========================================
    # MÉTODOS DE VALIDACIÓN AVANZADA
    # ==========================================
    
    def _validate_loan_serial_tracking(self):
        """Validar tracking por serie en movimientos de préstamo"""
        for move in self:
            if move.is_loan_move and move.product_id.tracking == 'serial':
                if move.quantity_done != len(move.move_line_ids.filtered('lot_id')):
                    raise ValidationError(_(
                        f"Para productos con número de serie en préstamos, "
                        f"cada unidad debe tener un número de serie único. "
                        f"Producto: {move.product_id.name}"
                    ))
    
    def _check_loan_return_availability(self):
        """Verificar disponibilidad para devoluciones"""
        for move in self:
            if move.is_loan_return_move and move.loan_return_qty:
                available_qty = move._get_available_return_qty()
                
                if move.loan_return_qty > available_qty:
                    raise ValidationError(_(
                        f"No se puede devolver {move.loan_return_qty:.2f} unidades de "
                        f"{move.product_id.name}. Solo hay {available_qty:.2f} disponibles "
                        f"para devolución del préstamo original."
                    ))
    
    # ==========================================
    # HOOKS PARA INTEGRACIÓN CON OTROS MÓDULOS
    # ==========================================
    
    def _prepare_procurement_values(self):
        """Preparar valores adicionales para aprovisionamiento en préstamos"""
        values = super()._prepare_procurement_values()
        
        if self.is_loan_move:
            # Agregar información específica de préstamo
            values.update({
                'loan_move': True,
                'loan_partner_id': self.picking_id.loaned_to_partner_id.id if self.picking_id else False,
            })
        
        return values


# ==========================================
# EXTENSIÓN DE STOCK MOVE LINE PARA COHERENCIA
# ==========================================

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    
    is_loan_move_line = fields.Boolean(
        string='Línea de Movimiento de Préstamo',
        related='move_id.is_loan_move',
        store=True,
        help="Indica si esta línea de movimiento es parte de un préstamo"
    )
    
    is_loan_return_move_line = fields.Boolean(
        string='Línea de Devolución de Préstamo',
        related='move_id.is_loan_return_move',
        store=True,
        help="Indica si esta línea es parte de una devolución de préstamo"
    )
    
    loan_tracking_reference = fields.Char(
        string='Referencia de Seguimiento',
        help="Referencia única para tracking de esta línea específica"
    )
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override para generar referencia de tracking automáticamente"""
        lines = super().create(vals_list)
        
        for line in lines:
            if line.is_loan_move_line and not line.loan_tracking_reference:
                # Generar referencia única
                reference = f"LOAN-{line.move_id.id}-{line.id}-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}"
                line.loan_tracking_reference = reference
        
        return lines
