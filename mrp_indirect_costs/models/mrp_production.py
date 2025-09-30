from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    
    landed_cost_id = fields.Many2one(
        'stock.landed.cost',
        string='Costo en destino',
        readonly=True,
        help='Costo en destino creado automáticamente para esta orden de fabricación'
    )
    
    # Reemplazar el campo related por el modelo proxy
    production_cost_line_ids = fields.One2many(
        'mrp.production.cost.line',
        'production_id',
        string='Líneas de costos indirectos'
    )
    
    def action_confirm(self):
        """Override para crear costo en destino automáticamente"""
        res = super().action_confirm()
        
        for production in self:
            if not production.landed_cost_id:
                production._create_landed_cost()
        
        return res

    def _get_default_landed_cost_journal(self):
        """Obtener el journal por defecto configurado para landed costs"""
        # Buscar en la configuración el journal por defecto para landed costs
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        # Intentar obtener el journal específico de stock/landed costs si existe
        stock_journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('code', 'ilike', 'STJ'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if stock_journal:
            return stock_journal
        
        return journal

    def _create_landed_cost(self):
        """Crear costo en destino con líneas automáticas para costos de fabricación (evitando duplicados)"""
        # Si ya existe un costo en destino, no hacer nada
        if self.landed_cost_id:
            return
        
        # Obtener el journal por defecto
        default_journal = self._get_default_landed_cost_journal()
        
        # Crear el costo en destino con el journal correcto
        landed_cost_vals = {
            'date': self.date_start or fields.Date.context_today(self),
            'target_model': 'manufacturing',
            'mrp_production_ids': [(4, self.id)],
            'company_id': self.company_id.id,
        }
        
        # Agregar el journal si se encontró uno
        if default_journal:
            landed_cost_vals['account_journal_id'] = default_journal.id
        
        landed_cost = self.env['stock.landed.cost'].create(landed_cost_vals)
        self.landed_cost_id = landed_cost.id
        
        # Buscar productos con costo en destino de fabricación
        manufacturing_cost_products = self.env['product.template'].search([
            ('is_landed_cost_manufacturing', '=', True)
        ])
        
        # Obtener productos que ya tienen líneas proxy para evitar duplicados
        existing_proxy_lines = self.production_cost_line_ids
        existing_product_ids = set()
        
        for proxy in existing_proxy_lines:
            if proxy.landed_cost_line_id and proxy.landed_cost_line_id.product_id:
                existing_product_ids.add(proxy.landed_cost_line_id.product_id.id)
        
        sequence = 10
        if existing_proxy_lines:
            # Si ya hay líneas, continuar la secuencia
            max_sequence = max(existing_proxy_lines.mapped('sequence') or [0])
            sequence = max_sequence + 10
        
        for product_tmpl in manufacturing_cost_products:
            # Buscar el producto específico (primera variante)
            product = product_tmpl.product_variant_ids[0] if product_tmpl.product_variant_ids else False
            if product and product.id not in existing_product_ids:
                # Crear la línea en landed cost solo si no existe
                landed_cost_line = self.env['stock.landed.cost.lines'].create({
                    'cost_id': landed_cost.id,
                    'product_id': product.id,
                    'name': product.name,  # Usar el nombre del producto
                    'price_unit': 0.0,
                    'split_method': 'equal',  # Método por defecto = igual
                })
                
                # Crear la línea proxy correspondiente
                self.env['mrp.production.cost.line'].create({
                    'production_id': self.id,
                    'landed_cost_line_id': landed_cost_line.id,
                    'sequence': sequence,
                })
                sequence += 10
    
    def button_mark_done(self):
        """Override para validar costos después de cerrar la producción"""
        # Primero verificar si hay líneas vacías para mostrar wizard
        for production in self:
            if production.production_cost_line_ids:
                empty_lines = production.production_cost_line_ids.filtered(lambda l: l.price_unit == 0.0)
                if empty_lines:
                    # Mostrar wizard de confirmación solo si hay líneas vacías
                    return production._show_cost_validation_wizard()
        
        # Ejecutar el cierre normal de la producción PRIMERO
        result = super().button_mark_done()
        
        # DESPUÉS validar landed costs (cuando la orden ya esté en estado 'done')
        for production in self:
            if production.production_cost_line_ids:
                production._validate_landed_cost_after_done()
        
        return result
    
    def _show_cost_validation_wizard(self):
        """Mostrar wizard de validación de costos"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Validación de Costos Indirectos'),
            'res_model': 'mrp.production.close.confirmation',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_production_id': self.id}
        }
    
    def _validate_landed_cost_after_done(self):
        """Validar landed cost DESPUÉS de completar la producción"""
        if self.landed_cost_id and self.landed_cost_id.state == 'draft':
            try:
                # Asegurar que la fecha esté establecida
                if not self.landed_cost_id.date:
                    self.landed_cost_id.date = self.date_finished or fields.Datetime.now()
                
                # Debug info
                self.message_post(
                    body=_("Iniciando validación de costo en destino después de completar producción. Estado: %s") % self.landed_cost_id.state,
                    message_type='comment'
                )
                
                # CRÍTICO: Ejecutar compute_landed_cost() ANTES de button_validate()
                # Esto debe generar los valuation_adjustment_lines para manufacturing
                self.landed_cost_id.compute_landed_cost()
                
                # Validar el costo en destino DESPUÉS de computar
                self.landed_cost_id.button_validate()
                
                # Mensaje de éxito
                self.message_post(
                    body=_("Costo en destino aplicado exitosamente a la valoración del producto."),
                    message_type='comment'
                )
            except Exception as e:
                # Solo mostrar advertencia, no bloquear
                self.message_post(
                    body=_("Advertencia al validar costo en destino: %s. La producción se completó correctamente.") % str(e),
                    message_type='comment'
                )
        elif self.landed_cost_id:
            self.message_post(
                body=_("Costo en destino ya está en estado: %s.") % self.landed_cost_id.state,
                message_type='comment'
            )
    
    def force_close_production(self):
        """Forzar cierre de producción validando costo en destino después (llamado desde wizard)"""
        # Cerrar la producción PRIMERO
        result = super().button_mark_done()
        
        # Después validar el costo en destino
        self._validate_landed_cost_after_done()
        
        return result
    
    def action_view_landed_cost(self):
        """Acción para ver el costo en destino"""
        self.ensure_one()
        if not self.landed_cost_id:
            return False
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Costo en Destino'),
            'res_model': 'stock.landed.cost',
            'res_id': self.landed_cost_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_add_cost_line(self):
        """Acción para agregar una línea de costo mediante formulario modal (alternativa al inline)"""
        self.ensure_one()
        
        if not self.landed_cost_id:
            self._create_landed_cost()
        
        # Verificar que el landed_cost_id existe
        if not self.landed_cost_id:
            raise UserError(_("No se pudo crear el costo en destino para esta orden de fabricación."))
        
        # Calcular secuencia para la nueva línea
        current_sequences = self.production_cost_line_ids.mapped('sequence')
        next_sequence = max(current_sequences) + 10 if current_sequences else 10
        
        # Abrir formulario modal (alternativo a edición inline)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nueva Línea de Costo'),
            'res_model': 'mrp.production.cost.line',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_production_id': self.id,
                'default_sequence': next_sequence,
            }
        }